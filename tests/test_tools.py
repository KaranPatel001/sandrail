from pathlib import Path

import pytest

from sandrail.sandbox import LocalSandbox
from sandrail.tools import PathEscapeError, Toolbox, default_tools, resolve_in_workspace


@pytest.fixture
def sb(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_bytes(b"def f():\n    return 1\n\n\ndef g():\n    return 1\n")
    (repo / "README.md").write_bytes(b"hello\n")
    with LocalSandbox(repo) as sandbox:
        yield sandbox


@pytest.fixture
def tb():
    return Toolbox(default_tools(command_timeout=30))


@pytest.mark.parametrize("bad", ["../outside.txt", "src/../../x", "/etc/passwd", "C:\\Windows\\win.ini", "C:/x", ""])
def test_resolve_rejects_escapes(tmp_path, bad):
    with pytest.raises(PathEscapeError):
        resolve_in_workspace(tmp_path, bad)


def test_resolve_allows_inside(tmp_path):
    assert resolve_in_workspace(tmp_path, "a/b/../c.txt") == (tmp_path / "a" / "c.txt").resolve()
    assert resolve_in_workspace(tmp_path, ".") == tmp_path.resolve()


def test_tool_specs_have_json_schemas(tb):
    specs = tb.specs()
    assert {s["name"] for s in specs} == {"list_files", "read_file", "edit_file", "write_file", "run_command"}
    for s in specs:
        schema = s["input_schema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) <= set(schema["properties"])
        assert s["description"]


def test_list_files(sb, tb):
    r = tb.call(sb, "list_files", {})
    assert not r.is_error
    assert r.output.splitlines() == ["README.md", "src/app.py"]
    assert tb.call(sb, "list_files", {"path": "src"}).output == "src/app.py"
    assert tb.call(sb, "list_files", {"path": "nope"}).is_error


def test_read_file_and_range(sb, tb):
    assert tb.call(sb, "read_file", {"path": "README.md"}).output == "hello\n"
    r = tb.call(sb, "read_file", {"path": "src/app.py", "start_line": 4, "end_line": 5})
    assert r.output == "\ndef g():\n"
    assert tb.call(sb, "read_file", {"path": "missing.py"}).is_error


def test_read_file_escape_is_error_not_exception(sb, tb):
    r = tb.call(sb, "read_file", {"path": "../../secret"})
    assert r.is_error and "escapes" in r.output


def test_edit_file_exact_replace(sb, tb):
    r = tb.call(sb, "edit_file", {"path": "src/app.py", "old_str": "def f():\n    return 1", "new_str": "def f():\n    return 2"})
    assert not r.is_error, r.output
    assert (sb.workspace / "src" / "app.py").read_bytes().startswith(b"def f():\n    return 2\n")


def test_edit_file_requires_unique_match(sb, tb):
    r = tb.call(sb, "edit_file", {"path": "src/app.py", "old_str": "return 1", "new_str": "return 3"})
    assert r.is_error and "2 times" in r.output
    r = tb.call(sb, "edit_file", {"path": "src/app.py", "old_str": "return 99", "new_str": "x"})
    assert r.is_error and "not found" in r.output
    r = tb.call(sb, "edit_file", {"path": "src/app.py", "old_str": "", "new_str": "x"})
    assert r.is_error


def test_write_file_creates_dirs(sb, tb):
    r = tb.call(sb, "write_file", {"path": "new/dir/x.py", "content": "A = 1\n"})
    assert not r.is_error
    assert (sb.workspace / "new" / "dir" / "x.py").read_bytes() == b"A = 1\n"


def test_write_file_cannot_escape(sb, tb, tmp_path):
    r = tb.call(sb, "write_file", {"path": "../evil.py", "content": "x"})
    assert r.is_error
    assert not (sb.workspace.parent / "evil.py").exists()


def test_run_command(sb, tb):
    r = tb.call(sb, "run_command", {"command": 'python -c "print(40 + 2)"'})
    assert not r.is_error
    assert r.output.startswith("exit code: 0")
    assert "42" in r.output
    r = tb.call(sb, "run_command", {"command": 'python -c "raise SystemExit(5)"'})
    assert r.is_error and r.output.startswith("exit code: 5")


def test_bad_inputs(sb, tb):
    assert "unknown tool" in tb.call(sb, "delete_everything", {}).output
    assert "missing required" in tb.call(sb, "read_file", {}).output
    assert "unknown argument" in tb.call(sb, "read_file", {"path": "README.md", "mode": "rb"}).output
    assert "type integer" in tb.call(sb, "read_file", {"path": "README.md", "start_line": "1"}).output
    assert "JSON object" in tb.call(sb, "read_file", ["README.md"]).output
