"""Command-line interface: ``sandrail run | validate | list``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agent import AgentConfig
from .grader import grade
from .runner import RunRecord, run_benchmark
from .sandbox import LocalSandbox
from .task import default_tasks_dir, load_tasks


def _progress(record: RunRecord) -> None:
    mark = "PASS" if record.passed and not record.flagged else "FAIL"
    flag = " [FLAGGED]" if record.flagged else ""
    print(f"  {mark}{flag}  {record.task_id} run {record.run}  steps={record.steps} status={record.status}", flush=True)


def cmd_run(args: argparse.Namespace) -> int:
    config = AgentConfig(
        max_steps=args.max_steps,
        token_budget=args.token_budget,
        command_timeout=args.command_timeout,
    )
    claude_kwargs = {}
    if not args.model.startswith("scripted:"):
        claude_kwargs = {"effort": args.effort, "fallbacks": not args.no_fallbacks}
    print(f"Running {args.model} on {args.tasks} ({args.runs} run(s) per task)")
    records, out_dir = run_benchmark(
        args.tasks,
        args.model,
        runs=args.runs,
        out_dir=args.out,
        config=config,
        sandbox_kind=args.sandbox,
        only=args.task or None,
        progress=_progress,
        **claude_kwargs,
    )
    clean = sum(r.passed and not r.flagged for r in records)
    flagged = sum(r.flagged for r in records)
    print(f"\n{clean}/{len(records)} runs passed cleanly, {flagged} flagged")
    print(f"Results: {out_dir / 'results.jsonl'}\nReport:  {out_dir / 'report.md'}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Check each task: hidden tests fail on the buggy repo and pass with the reference fix."""
    ok = True
    for task in load_tasks(args.tasks, args.task or None):
        with LocalSandbox(task.repo_dir) as sb:
            before = grade(task, sb.workspace)
        with LocalSandbox(task.repo_dir) as sb:
            for rel, src in task.solution_files().items():
                dest = sb.workspace / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(src.read_bytes())
            after = grade(task, sb.workspace)
        good = (not before.passed) and after.passed and not after.flagged
        ok &= good
        print(f"  {'ok  ' if good else 'BAD '} {task.id}: buggy={'pass' if before.passed else 'fail'} "
              f"fixed={'pass' if after.passed else 'fail'}")
    return 0 if ok else 1


def cmd_list(args: argparse.Namespace) -> int:
    for task in load_tasks(args.tasks):
        print(f"{task.id:24} {task.difficulty:7} {task.title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sandrail", description="Coding-agent harness and hidden-test benchmark.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a model on a set of tasks")
    run.add_argument("--tasks", type=Path, default=None, help="task directory (default: the bundled starter set)")
    run.add_argument("--model", default="claude-opus-5-5",
                     help="Claude model id, or scripted:reference / scripted:cheat / scripted:noop")
    run.add_argument("--runs", type=int, default=1)
    run.add_argument("--out", type=Path, default=None, help="output directory (default results/<time>-<model>)")
    run.add_argument("--task", action="append", help="only run this task id (repeatable)")
    run.add_argument("--sandbox", choices=["local", "docker"], default="local")
    run.add_argument("--max-steps", type=int, default=30)
    run.add_argument("--token-budget", type=int, default=400_000)
    run.add_argument("--command-timeout", type=float, default=60.0)
    run.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    run.add_argument("--no-fallbacks", action="store_true", help="disable server-side refusal fallback")
    run.set_defaults(func=cmd_run)

    val = sub.add_parser("validate", help="check that every task is fail-before / pass-after")
    val.add_argument("--tasks", type=Path, default=None, help="task directory (default: the bundled starter set)")
    val.add_argument("--task", action="append")
    val.set_defaults(func=cmd_validate)

    ls = sub.add_parser("list", help="list tasks")
    ls.add_argument("--tasks", type=Path, default=None, help="task directory (default: the bundled starter set)")
    ls.set_defaults(func=cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(args, "tasks") and args.tasks is None:
        args.tasks = default_tasks_dir()
    if getattr(args, "runs", 1) < 1:
        print("--runs must be at least 1", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
