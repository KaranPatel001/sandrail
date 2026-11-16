"""Benchmark runner: tasks x runs -> trajectories, results JSONL, report."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .agent import Agent, AgentConfig
from .baselines import BASELINES
from .grader import grade
from .models.base import Model
from .pricing import estimate_cost
from .report import write_report
from .sandbox import make_sandbox
from .task import Task, load_tasks

ModelFactory = Callable[[Task], Model]


def model_factory(spec: str, **claude_kwargs) -> ModelFactory:
    """Turn a ``--model`` value into a per-task model constructor.

    ``scripted:*`` names select an offline baseline; anything else is passed
    to the Claude adapter as a model id.
    """
    if spec in BASELINES:
        return BASELINES[spec]
    if spec.startswith("scripted:"):
        raise ValueError(f"unknown scripted baseline {spec!r}; choose from {', '.join(BASELINES)}")

    from .models.claude import ClaudeModel

    shared: dict[str, Model] = {}

    def make(_task: Task) -> Model:
        if "m" not in shared:
            shared["m"] = ClaudeModel(model=spec, **claude_kwargs)
        return shared["m"]

    return make


@dataclass
class RunRecord:
    task_id: str
    run: int
    model: str
    status: str
    steps: int
    tool_calls: int
    usage: dict
    cost_usd: float | None
    duration: float
    passed: bool
    flagged: bool
    flags: list[dict]
    tests_passed: int
    tests_failed: int
    applied: list[str]
    discarded: list[str]
    trajectory: str
    served_by: list[str] = field(default_factory=list)
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False)


def run_one(
    task: Task,
    run_index: int,
    make_model: ModelFactory,
    out_dir: Path,
    config: AgentConfig,
    sandbox_kind: str = "local",
) -> RunRecord:
    model = make_model(task)
    traj_path = out_dir / "trajectories" / f"{task.id}__run{run_index}.jsonl"
    with make_sandbox(sandbox_kind, task.repo_dir) as sb:
        agent = Agent(model, config)
        result = agent.run(task.prompt(), sb, traj_path, meta={"task_id": task.id, "run": run_index})
        graded = grade(task, sb.workspace, lambda src: make_sandbox(sandbox_kind, src))
    return RunRecord(
        task_id=task.id,
        run=run_index,
        model=model.name,
        status=result.status,
        steps=result.steps,
        tool_calls=result.tool_calls,
        usage=result.usage.to_dict(),
        cost_usd=estimate_cost(model.name, result.usage),
        duration=round(result.duration, 3),
        passed=graded.passed,
        flagged=graded.flagged,
        flags=[f.__dict__ for f in graded.flags],
        tests_passed=graded.tests_passed,
        tests_failed=graded.tests_failed,
        applied=graded.applied,
        discarded=graded.discarded,
        trajectory=traj_path.relative_to(out_dir).as_posix(),
        served_by=result.served_by,
        error=result.error,
    )


def run_benchmark(
    tasks_path: Path | str,
    model: str,
    runs: int = 1,
    out_dir: Path | str | None = None,
    config: AgentConfig | None = None,
    sandbox_kind: str = "local",
    only: list[str] | None = None,
    make_model: ModelFactory | None = None,
    progress: Callable[[RunRecord], None] | None = None,
    **claude_kwargs,
) -> tuple[list[RunRecord], Path]:
    tasks = load_tasks(tasks_path, only)
    config = config or AgentConfig()
    make_model = make_model or model_factory(model, **claude_kwargs)
    if out_dir is None:
        safe = model.replace(":", "-").replace("/", "-")
        out_dir = Path("results") / f"{time.strftime('%Y%m%d-%H%M%S')}-{safe}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records: list[RunRecord] = []
    results_path = out_dir / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as fh:
        for task in tasks:
            for i in range(1, runs + 1):
                record = run_one(task, i, make_model, out_dir, config, sandbox_kind)
                records.append(record)
                fh.write(record.to_json() + "\n")
                fh.flush()
                if progress:
                    progress(record)

    write_report(records, out_dir / "report.md", model=model, tasks_path=str(tasks_path), runs=runs)
    return records, out_dir
