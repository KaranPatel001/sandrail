"""Sandboxes: isolated copies of a task repo where agent commands run.

``LocalSandbox`` copies the repo to a temp dir and runs commands with
``subprocess`` under a timeout. ``DockerSandbox`` does the same copy but runs
each command in a throwaway container with ``--network none`` and the
workspace bind-mounted, which is the setting to use for untrusted models.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

# Directories never copied into (or diffed out of) a workspace.
IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", ".ruff_cache"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}

# Environment variables whose names contain these fragments are scrubbed
# before a command runs, so an agent cannot read API keys from the host.
_SECRET_FRAGMENTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration: float = 0.0

    @property
    def output(self) -> str:
        """stdout and stderr combined, the way a terminal shows them."""
        parts = [self.stdout]
        if self.stderr:
            parts.append(self.stderr)
        text = "\n".join(p for p in parts if p)
        if self.timed_out:
            text += "\n[command timed out]"
        return text


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in IGNORED_DIRS or Path(n).suffix in IGNORED_SUFFIXES}


def copy_repo(source: Path, dest: Path) -> None:
    shutil.copytree(source, dest, ignore=_ignore, dirs_exist_ok=True)


def scrubbed_env() -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(fragment in k.upper() for fragment in _SECRET_FRAGMENTS)
    }
    # Make `python` resolve to the interpreter running Sandrail, so tasks get
    # the same pytest install without depending on the host PATH order.
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    return env


class Sandbox(ABC):
    """A workspace directory plus a way to run shell commands inside it."""

    def __init__(self, source: Path | str):
        self.source = Path(source)
        self._tmp = tempfile.mkdtemp(prefix="sandrail-")
        self.workspace = Path(self._tmp) / "workspace"
        copy_repo(self.source, self.workspace)

    @abstractmethod
    def run(self, command: str, timeout: float = 60.0) -> CommandResult:
        """Run a shell command with the workspace as the working directory."""

    def close(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _kill_tree(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.kill()


class LocalSandbox(Sandbox):
    """Runs commands directly on the host, in a temp copy of the repo.

    This isolates the filesystem view (the agent edits a copy) but not the
    process: commands still have host network and can read outside the
    workspace. Use ``DockerSandbox`` when that matters.
    """

    def run(self, command: str, timeout: float = 60.0) -> CommandResult:
        start = time.monotonic()
        kwargs: dict = {}
        if sys.platform != "win32":
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=self.workspace,
            env=scrubbed_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            stdout, stderr = proc.communicate()
            timed_out = True
        return CommandResult(
            exit_code=proc.returncode if not timed_out else -1,
            stdout=stdout or "",
            stderr=stderr or "",
            timed_out=timed_out,
            duration=time.monotonic() - start,
        )


class DockerSandbox(Sandbox):
    """Runs each command in a fresh container with no network access.

    The workspace is bind-mounted at ``/workspace``. The image must already
    contain Python and pytest (see ``docker/Dockerfile``).
    """

    def __init__(
        self,
        source: Path | str,
        image: str = "sandrail-python:3.12",
        memory: str = "1g",
        cpus: str = "1",
        docker: str = "docker",
    ):
        super().__init__(source)
        self.image = image
        self.memory = memory
        self.cpus = cpus
        self.docker = docker

    @staticmethod
    def available(docker: str = "docker") -> bool:
        return shutil.which(docker) is not None

    def docker_args(self, command: str) -> list[str]:
        return [
            self.docker,
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            self.memory,
            "--cpus",
            self.cpus,
            "--pids-limit",
            "256",
            "-v",
            f"{self.workspace.resolve()}:/workspace",
            "-w",
            "/workspace",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            self.image,
            "sh",
            "-c",
            command,
        ]

    def run(self, command: str, timeout: float = 60.0) -> CommandResult:
        start = time.monotonic()
        try:
            proc = subprocess.run(
                self.docker_args(command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                exit_code=-1,
                stdout=_as_text(exc.stdout),
                stderr=_as_text(exc.stderr),
                timed_out=True,
                duration=time.monotonic() - start,
            )
        return CommandResult(
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            duration=time.monotonic() - start,
        )


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def make_sandbox(kind: str, source: Path | str) -> Sandbox:
    if kind == "local":
        return LocalSandbox(source)
    if kind == "docker":
        return DockerSandbox(source)
    raise ValueError(f"unknown sandbox kind: {kind!r} (expected 'local' or 'docker')")
