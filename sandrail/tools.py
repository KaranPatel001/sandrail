"""Agent tools. Every path is resolved inside the sandbox workspace.

Each tool carries a JSON schema (``input_schema``) that model adapters pass
to the provider for tool calling. Tools return a ``ToolResult``; they never
raise for bad model input, because the model needs the error text to recover.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .sandbox import IGNORED_DIRS, Sandbox

MAX_LIST_ENTRIES = 500
MAX_READ_BYTES = 200_000


class PathEscapeError(ValueError):
    pass


@dataclass
class ToolResult:
    output: str
    is_error: bool = False


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[[Sandbox, dict[str, Any]], ToolResult]

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def resolve_in_workspace(workspace: Path, path: str) -> Path:
    """Map a model-supplied relative path to a real path inside ``workspace``.

    Rejects absolute paths, drive letters, and anything that resolves outside
    the workspace (``..`` segments or symlinks pointing out).
    """
    if not isinstance(path, str) or path.strip() == "":
        raise PathEscapeError("path must be a non-empty string")
    raw = path.replace("\\", "/")
    if raw.startswith("/") or PurePosixPath(raw).is_absolute() or (len(raw) > 1 and raw[1] == ":"):
        raise PathEscapeError(f"absolute paths are not allowed: {path!r}")
    root = workspace.resolve()
    target = (root / raw).resolve()
    if target != root and not target.is_relative_to(root):
        raise PathEscapeError(f"path escapes the workspace: {path!r}")
    return target


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _check_args(tool: Tool, args: Any) -> str | None:
    if not isinstance(args, dict):
        return "tool input must be a JSON object"
    schema = tool.input_schema
    missing = [k for k in schema.get("required", []) if k not in args]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    unknown = [k for k in args if k not in schema["properties"]]
    if unknown:
        return f"unknown argument(s): {', '.join(unknown)}"
    types = {"string": str, "integer": int}
    for key, value in args.items():
        expected = schema["properties"][key].get("type")
        py = types.get(expected)
        if py is not None and (not isinstance(value, py) or isinstance(value, bool)):
            return f"argument {key!r} must be of type {expected}"
    return None


def _rel(workspace: Path, p: Path) -> str:
    return p.relative_to(workspace.resolve()).as_posix()


def list_files(sb: Sandbox, args: dict[str, Any]) -> ToolResult:
    base = resolve_in_workspace(sb.workspace, args.get("path", "."))
    if not base.exists():
        return ToolResult(f"no such directory: {args.get('path', '.')}", is_error=True)
    if base.is_file():
        return ToolResult(_rel(sb.workspace, base))
    entries: list[str] = []
    for p in sorted(base.rglob("*")):
        rel_parts = p.relative_to(base).parts
        if any(part in IGNORED_DIRS for part in rel_parts) or p.suffix == ".pyc":
            continue
        if p.is_file():
            entries.append(_rel(sb.workspace, p))
        if len(entries) >= MAX_LIST_ENTRIES:
            entries.append(f"... (truncated at {MAX_LIST_ENTRIES} entries)")
            break
    return ToolResult("\n".join(entries) if entries else "(empty directory)")


def read_file(sb: Sandbox, args: dict[str, Any]) -> ToolResult:
    target = resolve_in_workspace(sb.workspace, args["path"])
    if not target.is_file():
        return ToolResult(f"no such file: {args['path']}", is_error=True)
    data = target.read_bytes()[:MAX_READ_BYTES]
    text = data.decode("utf-8", errors="replace")
    start = args.get("start_line")
    end = args.get("end_line")
    if start is not None or end is not None:
        lines = text.splitlines(keepends=True)
        lo = max((start or 1) - 1, 0)
        hi = end if end is not None else len(lines)
        text = "".join(lines[lo:hi])
    return ToolResult(text)


def edit_file(sb: Sandbox, args: dict[str, Any]) -> ToolResult:
    target = resolve_in_workspace(sb.workspace, args["path"])
    if not target.is_file():
        return ToolResult(f"no such file: {args['path']}", is_error=True)
    old, new = args["old_str"], args["new_str"]
    if old == "":
        return ToolResult("old_str must not be empty", is_error=True)
    # Bytes in, bytes out: no newline translation, so line endings are preserved.
    text = target.read_bytes().decode("utf-8")
    count = text.count(old)
    if count == 0:
        return ToolResult("old_str was not found in the file; read the file and copy the text exactly", is_error=True)
    if count > 1:
        return ToolResult(f"old_str appears {count} times; include more context so it is unique", is_error=True)
    target.write_bytes(text.replace(old, new, 1).encode("utf-8"))
    return ToolResult(f"edited {_rel(sb.workspace, target)}")


def write_file(sb: Sandbox, args: dict[str, Any]) -> ToolResult:
    target = resolve_in_workspace(sb.workspace, args["path"])
    if target.is_dir():
        return ToolResult(f"{args['path']} is a directory", is_error=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(args["content"].encode("utf-8"))
    return ToolResult(f"wrote {len(args['content'])} chars to {_rel(sb.workspace, target)}")


def make_run_command(default_timeout: float, max_timeout: float) -> Callable[[Sandbox, dict[str, Any]], ToolResult]:
    def run_command(sb: Sandbox, args: dict[str, Any]) -> ToolResult:
        timeout = min(float(args.get("timeout", default_timeout)), max_timeout)
        result = sb.run(args["command"], timeout=timeout)
        body = result.output or "(no output)"
        return ToolResult(f"exit code: {result.exit_code}\n{body}", is_error=result.exit_code != 0)

    return run_command


def default_tools(command_timeout: float = 60.0, max_command_timeout: float = 300.0) -> list[Tool]:
    return [
        Tool(
            "list_files",
            "List files under a directory of the repository (recursive). Paths are relative to the repo root.",
            _schema({"path": {"type": "string", "description": "Directory relative to the repo root. Defaults to '.'."}}, []),
            list_files,
        ),
        Tool(
            "read_file",
            "Read a UTF-8 text file from the repository. Optionally restrict to a 1-based inclusive line range.",
            _schema(
                {
                    "path": {"type": "string", "description": "File path relative to the repo root."},
                    "start_line": {"type": "integer", "description": "First line to return (1-based)."},
                    "end_line": {"type": "integer", "description": "Last line to return (inclusive)."},
                },
                ["path"],
            ),
            read_file,
        ),
        Tool(
            "edit_file",
            "Replace one exact occurrence of old_str with new_str in a file. old_str must match the file "
            "byte-for-byte (including indentation) and occur exactly once.",
            _schema(
                {
                    "path": {"type": "string", "description": "File path relative to the repo root."},
                    "old_str": {"type": "string", "description": "Exact text to replace; must be unique in the file."},
                    "new_str": {"type": "string", "description": "Replacement text."},
                },
                ["path", "old_str", "new_str"],
            ),
            edit_file,
        ),
        Tool(
            "write_file",
            "Create or overwrite a file with the given content. Parent directories are created as needed.",
            _schema(
                {
                    "path": {"type": "string", "description": "File path relative to the repo root."},
                    "content": {"type": "string", "description": "Full file content."},
                },
                ["path", "content"],
            ),
            write_file,
        ),
        Tool(
            "run_command",
            "Run a shell command from the repo root, for example `python -m pytest -q`. Returns the exit code "
            "and combined output (long output is trimmed).",
            _schema(
                {
                    "command": {"type": "string", "description": "Shell command to run."},
                    "timeout": {"type": "integer", "description": f"Seconds before the command is killed (max {int(max_command_timeout)})."},
                },
                ["command"],
            ),
            make_run_command(command_timeout, max_command_timeout),
        ),
    ]


class Toolbox:
    """Dispatches model tool calls to tools, turning every failure into a ToolResult."""

    def __init__(self, tools: list[Tool]):
        self.tools = {t.name: t for t in tools}

    def specs(self) -> list[dict[str, Any]]:
        return [t.spec() for t in self.tools.values()]

    def call(self, sb: Sandbox, name: str, args: Any) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult(f"unknown tool: {name!r}. Available: {', '.join(self.tools)}", is_error=True)
        problem = _check_args(tool, args)
        if problem:
            return ToolResult(problem, is_error=True)
        try:
            return tool.fn(sb, args)
        except PathEscapeError as exc:
            return ToolResult(str(exc), is_error=True)
        except (OSError, UnicodeDecodeError) as exc:
            return ToolResult(f"{type(exc).__name__}: {exc}", is_error=True)
