import subprocess
from pathlib import Path

import pytest

from sandrail import sandbox as sandbox_mod
from sandrail.sandbox import CommandResult, DockerSandbox, LocalSandbox, make_sandbox


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "mod.py").write_text("X = 1\n")
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "junk.pyc").write_bytes(b"\0")
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    return repo


def test_local_sandbox_copies_repo_without_caches(tmp_path):
    repo = make_repo(tmp_path)
    with LocalSandbox(repo) as sb:
        assert (sb.workspace / "pkg" / "mod.py").read_text() == "X = 1\n"
        assert not (sb.workspace / "__pycache__").exists()
        assert not (sb.workspace / ".git").exists()
        assert sb.workspace.resolve() != repo.resolve()


def test_local_sandbox_edits_do_not_touch_source(tmp_path):
    repo = make_repo(tmp_path)
    with LocalSandbox(repo) as sb:
        (sb.workspace / "pkg" / "mod.py").write_text("X = 2\n")
    assert (repo / "pkg" / "mod.py").read_text() == "X = 1\n"


def test_local_sandbox_runs_in_workspace(tmp_path):
    repo = make_repo(tmp_path)
    with LocalSandbox(repo) as sb:
        result = sb.run('python -c "import pkg.mod as m; print(m.X)"')
        assert result.exit_code == 0
        assert result.stdout.strip() == "1"


def test_local_sandbox_nonzero_exit(tmp_path):
    with LocalSandbox(make_repo(tmp_path)) as sb:
        result = sb.run('python -c "import sys; sys.exit(3)"')
        assert result.exit_code == 3
        assert not result.timed_out


def test_local_sandbox_timeout(tmp_path):
    with LocalSandbox(make_repo(tmp_path)) as sb:
        result = sb.run('python -c "import time; time.sleep(30)"', timeout=1)
        assert result.timed_out
        assert result.exit_code == -1
        assert "timed out" in result.output
        assert result.duration < 20


def test_local_sandbox_scrubs_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDRAIL_FAKE_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("SANDRAIL_PLAIN", "visible")
    with LocalSandbox(make_repo(tmp_path)) as sb:
        result = sb.run(
            'python -c "import os; print(os.environ.get(\'SANDRAIL_FAKE_API_KEY\'), os.environ.get(\'SANDRAIL_PLAIN\'))"'
        )
    assert result.stdout.split() == ["None", "visible"]


def test_close_removes_temp_dir(tmp_path):
    sb = LocalSandbox(make_repo(tmp_path))
    ws = sb.workspace
    sb.close()
    assert not ws.exists()


def test_command_result_output_combines_streams():
    r = CommandResult(1, "out", "err", timed_out=True)
    assert r.output == "out\nerr\n[command timed out]"


def test_make_sandbox(tmp_path):
    with make_sandbox("local", make_repo(tmp_path)) as sb:
        assert isinstance(sb, LocalSandbox)
    with pytest.raises(ValueError):
        make_sandbox("vm", tmp_path)


# --- DockerSandbox (docker itself is mocked) ---------------------------------


def test_docker_args_isolate_network_and_mount_workspace(tmp_path):
    with DockerSandbox(make_repo(tmp_path), image="img:1") as sb:
        args = sb.docker_args("python -m pytest -q")
        assert args[:3] == ["docker", "run", "--rm"]
        assert args[args.index("--network") + 1] == "none"
        assert f"{sb.workspace.resolve()}:/workspace" in args
        assert args[args.index("-w") + 1] == "/workspace"
        assert args[-4:] == ["img:1", "sh", "-c", "python -m pytest -q"]
        assert "--memory" in args and "--pids-limit" in args


def test_docker_run_uses_subprocess(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="2 passed\n", stderr="")

    monkeypatch.setattr(sandbox_mod.subprocess, "run", fake_run)
    with DockerSandbox(make_repo(tmp_path)) as sb:
        result = sb.run("python -m pytest -q", timeout=42)
    assert result.exit_code == 0
    assert result.stdout == "2 passed\n"
    (args, kwargs), = calls
    assert args[0] == "docker" and "--network" in args
    assert kwargs["timeout"] == 42


def test_docker_run_timeout(tmp_path, monkeypatch):
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs["timeout"], output=b"partial", stderr=None)

    monkeypatch.setattr(sandbox_mod.subprocess, "run", fake_run)
    with DockerSandbox(make_repo(tmp_path)) as sb:
        result = sb.run("sleep 100", timeout=1)
    assert result.timed_out
    assert result.exit_code == -1
    assert result.stdout == "partial"


def test_docker_available(monkeypatch):
    monkeypatch.setattr(sandbox_mod.shutil, "which", lambda name: None)
    assert DockerSandbox.available() is False
    monkeypatch.setattr(sandbox_mod.shutil, "which", lambda name: "/usr/bin/docker")
    assert DockerSandbox.available() is True
