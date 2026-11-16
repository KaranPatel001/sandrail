"""Benchmark task layout and loading.

A task is a directory::

    <task-id>/
      task.yaml        # id, title, instruction, optional test_command/timeout/tags
      repo/            # the buggy repository the agent sees
      hidden_tests/    # copied into the repo only at grading time
      solution/        # reference fix (files at repo-relative paths), never shown to the agent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_TEST_COMMAND = "python -m pytest -q -p no:cacheprovider"


@dataclass
class Task:
    id: str
    title: str
    instruction: str
    root: Path
    test_command: str = DEFAULT_TEST_COMMAND
    timeout: float = 120.0
    difficulty: str = "easy"
    tags: list[str] = field(default_factory=list)

    @property
    def repo_dir(self) -> Path:
        return self.root / "repo"

    @property
    def hidden_tests_dir(self) -> Path:
        return self.root / "hidden_tests"

    @property
    def solution_dir(self) -> Path:
        return self.root / "solution"

    def files_under(self, base: Path) -> dict[str, Path]:
        if not base.is_dir():
            return {}
        return {
            p.relative_to(base).as_posix(): p
            for p in sorted(base.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        }

    def hidden_test_files(self) -> dict[str, Path]:
        return self.files_under(self.hidden_tests_dir)

    def solution_files(self) -> dict[str, Path]:
        return self.files_under(self.solution_dir)

    def prompt(self) -> str:
        return f"# {self.title}\n\n{self.instruction.strip()}\n"


def load_task(root: Path) -> Task:
    root = Path(root)
    spec = yaml.safe_load((root / "task.yaml").read_text(encoding="utf-8")) or {}
    for key in ("id", "title", "instruction"):
        if key not in spec:
            raise ValueError(f"{root / 'task.yaml'}: missing required key {key!r}")
    if not (root / "repo").is_dir():
        raise ValueError(f"{root}: missing repo/ directory")
    if not (root / "hidden_tests").is_dir():
        raise ValueError(f"{root}: missing hidden_tests/ directory")
    return Task(
        id=str(spec["id"]),
        title=str(spec["title"]),
        instruction=str(spec["instruction"]),
        root=root,
        test_command=str(spec.get("test_command", DEFAULT_TEST_COMMAND)),
        timeout=float(spec.get("timeout", 120)),
        difficulty=str(spec.get("difficulty", "easy")),
        tags=list(spec.get("tags", [])),
    )


def load_tasks(path: Path | str, only: list[str] | None = None) -> list[Task]:
    path = Path(path)
    if (path / "task.yaml").is_file():
        tasks = [load_task(path)]
    else:
        tasks = [load_task(p.parent) for p in sorted(path.glob("*/task.yaml"))]
    if only:
        wanted = set(only)
        tasks = [t for t in tasks if t.id in wanted]
    if not tasks:
        raise ValueError(f"no tasks found under {path}")
    return tasks
