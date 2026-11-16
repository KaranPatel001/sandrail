"""End-to-end checks on the starter benchmark with scripted baselines."""

import json

import pytest

from sandrail.grader import grade
from sandrail.runner import model_factory, run_benchmark
from sandrail.sandbox import LocalSandbox
from sandrail.task import load_tasks

from .conftest import STARTER

TASKS = load_tasks(STARTER)


def test_starter_has_twelve_tasks():
    assert len(TASKS) == 12
    assert len({t.id for t in TASKS}) == 12
    for t in TASKS:
        assert t.instruction.strip()
        assert t.hidden_test_files(), t.id
        assert t.solution_files(), t.id
        # Hidden tests must never be visible in the agent's repo.
        assert not set(t.hidden_test_files()) & set(t.files_under(t.repo_dir)), t.id


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_task_is_fail_before_pass_after(task):
    with LocalSandbox(task.repo_dir) as sb:
        assert sb.run(task.test_command, timeout=task.timeout).exit_code == 0, "visible tests should pass on the buggy repo"
        assert not grade(task, sb.workspace).passed, "hidden tests should fail on the buggy repo"
    with LocalSandbox(task.repo_dir) as sb:
        for rel, src in task.solution_files().items():
            (sb.workspace / rel).write_bytes(src.read_bytes())
        result = grade(task, sb.workspace)
    assert result.passed and not result.flagged, result.output_tail


def test_reference_run_solves_every_task(tmp_path):
    records, out = run_benchmark(STARTER, "scripted:reference", runs=1, out_dir=tmp_path)
    assert len(records) == 12
    assert all(r.passed and not r.flagged for r in records), [r.task_id for r in records if not r.passed]
    assert all(r.status == "completed" for r in records)
    assert all(r.cost_usd == 0.0 for r in records)

    lines = (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 12
    assert json.loads(lines[0])["passed"] is True
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "12/12 (100.0%)" in report
    assert "| Runs flagged for reward hacking | 0 |" in report
    for r in records:
        assert (out / r.trajectory).is_file()


def test_cheating_run_is_flagged_and_scores_zero(tmp_path):
    records, out = run_benchmark(STARTER, "scripted:cheat", runs=1, out_dir=tmp_path)
    assert len(records) == 12
    assert all(r.flagged for r in records)
    assert not any(r.passed for r in records)
    for r in records:
        flagged_paths = {f["path"] for f in r.flags}
        assert "conftest.py" in flagged_paths
        assert any(p.startswith("tests/") for p in flagged_paths)
        assert r.applied == []
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "0/12 (0.0%)" in report
    assert "| Runs flagged for reward hacking | 12 |" in report
    assert "conftest.py can alter test collection or results" in report


def test_noop_run_fails_unflagged(tmp_path):
    records, _ = run_benchmark(STARTER, "scripted:noop", out_dir=tmp_path, only=["slugify-separators", "semver-numeric-compare"])
    assert [r.passed for r in records] == [False, False]
    assert not any(r.flagged for r in records)


def test_multiple_runs(tmp_path):
    records, out = run_benchmark(STARTER, "scripted:reference", runs=2, out_dir=tmp_path, only=["paginate-last-page"])
    assert [(r.task_id, r.run) for r in records] == [("paginate-last-page", 1), ("paginate-last-page", 2)]
    assert "Tasks solved in every run (pass^2) | 1/1" in (out / "report.md").read_text(encoding="utf-8")


def test_unknown_scripted_model():
    with pytest.raises(ValueError):
        model_factory("scripted:oracle")
