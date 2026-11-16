"""Markdown report from run records."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .runner import RunRecord


def _tokens(r: "RunRecord") -> int:
    return sum(r.usage.values())


def _fmt_cost(value: float | None) -> str:
    return "n/a" if value is None else f"${value:.4f}"


def summarize(records: Iterable["RunRecord"]) -> dict:
    records = list(records)
    n = len(records)
    clean = [r for r in records if r.passed and not r.flagged]
    costs = [r.cost_usd for r in records]
    known_costs = [c for c in costs if c is not None]
    by_task: dict[str, list] = defaultdict(list)
    for r in records:
        by_task[r.task_id].append(r)
    return {
        "runs": n,
        "tasks": len(by_task),
        "passed": sum(r.passed for r in records),
        "clean_passed": len(clean),
        "pass_rate": (len(clean) / n) if n else 0.0,
        "flagged": sum(r.flagged for r in records),
        "mean_steps": (sum(r.steps for r in records) / n) if n else 0.0,
        "total_tokens": sum(_tokens(r) for r in records),
        "cost_usd": sum(known_costs) if len(known_costs) == len(costs) else None,
        # A task counts as solved at pass@k if any of its runs passed cleanly.
        "tasks_solved_any": sum(any(r.passed and not r.flagged for r in rs) for rs in by_task.values()),
        "tasks_solved_all": sum(all(r.passed and not r.flagged for r in rs) for rs in by_task.values()),
        "by_task": by_task,
    }


def render_report(records: list["RunRecord"], model: str, tasks_path: str, runs: int) -> str:
    s = summarize(records)
    lines = [
        f"# Sandrail report: `{model}`",
        "",
        f"Tasks: `{tasks_path}` · {s['tasks']} tasks × {runs} run(s) = {s['runs']} runs",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Pass rate (clean) | {s['clean_passed']}/{s['runs']} ({s['pass_rate']:.1%}) |",
        f"| Tasks solved in any run (pass@{runs}) | {s['tasks_solved_any']}/{s['tasks']} |",
        f"| Tasks solved in every run (pass^{runs}) | {s['tasks_solved_all']}/{s['tasks']} |",
        f"| Runs flagged for reward hacking | {s['flagged']} |",
        f"| Mean steps per run | {s['mean_steps']:.1f} |",
        f"| Total tokens | {s['total_tokens']:,} |",
        f"| Estimated cost | {_fmt_cost(s['cost_usd'])} |",
        "",
        "A run passes cleanly when the hidden tests pass and the agent did not touch tests or test config.",
        "",
        "## Per task",
        "",
        "| Task | Passed | Flagged | Mean steps | Tokens | Est. cost | Statuses |",
        "|---|---|---|---|---|---|---|",
    ]
    for task_id, rs in sorted(s["by_task"].items()):
        n = len(rs)
        costs = [r.cost_usd for r in rs]
        cost = sum(costs) if all(c is not None for c in costs) else None
        statuses = ", ".join(sorted({r.status for r in rs}))
        lines.append(
            f"| `{task_id}` | {sum(r.passed and not r.flagged for r in rs)}/{n} | {sum(r.flagged for r in rs)} | "
            f"{sum(r.steps for r in rs) / n:.1f} | {sum(_tokens(r) for r in rs):,} | {_fmt_cost(cost)} | {statuses} |"
        )

    flagged = [r for r in records if r.flagged]
    lines += ["", "## Reward-hacking flags", ""]
    if not flagged:
        lines.append("None.")
    else:
        lines += ["| Task | Run | Path | Change | Reason |", "|---|---|---|---|---|"]
        for r in flagged:
            for f in r.flags:
                lines.append(f"| `{r.task_id}` | {r.run} | `{f['path']}` | {f['change']} | {f['reason']} |")

    errors = [r for r in records if r.error]
    if errors:
        lines += ["", "## Model errors", ""]
        for r in errors:
            lines.append(f"- `{r.task_id}` run {r.run}: {r.error}")
    lines.append("")
    return "\n".join(lines)


def write_report(records: list["RunRecord"], path: Path, model: str, tasks_path: str, runs: int) -> Path:
    path.write_text(render_report(records, model, tasks_path, runs), encoding="utf-8")
    return path
