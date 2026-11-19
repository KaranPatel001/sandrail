"""Resuming an interrupted benchmark run."""

import json

import pytest

from sandrail.cli import main
from sandrail.models.base import Model
from sandrail.models.scripted import ScriptedModel
from sandrail.runner import load_records, run_benchmark

from .conftest import STARTER

TASKS = ["lru-get-recency", "paginate-last-page", "query-string-equals"]


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def counting_factory(calls, name="scripted:noop"):
    """A model factory that records which tasks actually ran."""

    def make(task):
        calls.append(task.id)
        return ScriptedModel(["Nothing to do."], name=name)

    return make


def test_resume_skips_finished_runs(tmp_path):
    first = []
    run_benchmark(STARTER, "scripted:noop", out_dir=tmp_path, only=TASKS[:2], make_model=counting_factory(first))
    assert sorted(first) == sorted(TASKS[:2])

    second = []
    records, _ = run_benchmark(
        STARTER, "scripted:noop", out_dir=tmp_path, only=TASKS, make_model=counting_factory(second), resume=True
    )
    assert second == [TASKS[2]]
    assert sorted(r.task_id for r in records) == sorted(TASKS)
    assert sorted(r["task_id"] for r in lines(tmp_path / "results.jsonl")) == sorted(TASKS)
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert all(f"`{task}`" in report for task in TASKS)  # the report covers kept and new runs


def test_resume_picks_up_extra_runs_per_task(tmp_path):
    run_benchmark(STARTER, "scripted:noop", runs=1, out_dir=tmp_path, only=TASKS[:1])
    calls = []
    records, _ = run_benchmark(
        STARTER, "scripted:noop", runs=3, out_dir=tmp_path, only=TASKS[:1],
        make_model=counting_factory(calls), resume=True,
    )
    assert len(calls) == 2
    assert [(r.task_id, r.run) for r in records] == [(TASKS[0], 1), (TASKS[0], 2), (TASKS[0], 3)]


def test_resume_reruns_model_errors(tmp_path):
    class Broken(Model):
        name = "scripted:noop"

        def complete(self, system, messages, tools):
            raise ValueError("provider is down")

    records, _ = run_benchmark(STARTER, "scripted:noop", out_dir=tmp_path, only=TASKS[:1], make_model=lambda t: Broken())
    assert records[0].status == "model_error"

    calls = []
    records, _ = run_benchmark(
        STARTER, "scripted:noop", out_dir=tmp_path, only=TASKS[:1], make_model=counting_factory(calls), resume=True
    )
    assert calls == TASKS[:1]
    assert [r.status for r in records] == ["completed"]
    assert len(lines(tmp_path / "results.jsonl")) == 1  # the failed record is replaced, not kept beside the new one


def test_resume_ignores_a_truncated_last_line(tmp_path):
    run_benchmark(STARTER, "scripted:noop", out_dir=tmp_path, only=TASKS[:2])
    results = tmp_path / "results.jsonl"
    whole, cut = results.read_text(encoding="utf-8").splitlines()
    results.write_text(whole + "\n" + cut[: len(cut) // 2], encoding="utf-8")
    assert [r.task_id for r in load_records(results)] == [json.loads(whole)["task_id"]]

    calls = []
    records, _ = run_benchmark(
        STARTER, "scripted:noop", out_dir=tmp_path, only=TASKS[:2], make_model=counting_factory(calls), resume=True
    )
    assert calls == [json.loads(cut)["task_id"]]  # only the run whose record was cut off
    assert len(records) == 2
    assert len(lines(results)) == 2


def test_resume_drops_records_outside_the_requested_set(tmp_path):
    run_benchmark(STARTER, "scripted:noop", out_dir=tmp_path, only=TASKS[:2])
    records, _ = run_benchmark(STARTER, "scripted:noop", out_dir=tmp_path, only=TASKS[:1], resume=True)
    assert [r.task_id for r in records] == TASKS[:1]
    assert [r["task_id"] for r in lines(tmp_path / "results.jsonl")] == TASKS[:1]


def test_without_resume_the_run_starts_over(tmp_path):
    run_benchmark(STARTER, "scripted:noop", out_dir=tmp_path, only=TASKS[:1])
    calls = []
    run_benchmark(STARTER, "scripted:noop", out_dir=tmp_path, only=TASKS[:1], make_model=counting_factory(calls))
    assert calls == TASKS[:1]


def test_resume_needs_an_output_directory():
    with pytest.raises(ValueError, match="output directory"):
        run_benchmark(STARTER, "scripted:noop", resume=True)


def test_cli_resume(tmp_path, capsys):
    args = ["run", "--tasks", str(STARTER), "--model", "scripted:reference"]
    assert main([*args, "--task", TASKS[0], "--out", str(tmp_path)]) == 0
    capsys.readouterr()

    assert main([*args, "--task", TASKS[0], "--task", TASKS[1], "--resume", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert f"Resuming {tmp_path}" in out
    assert f"PASS  {TASKS[1]} run 1" in out
    assert f"{TASKS[0]} run 1" not in out  # kept from the first invocation, not run again
    assert "2/2 runs passed cleanly" in out


def test_cli_resume_rejects_a_missing_run_and_a_conflicting_out(tmp_path, capsys):
    args = ["run", "--tasks", str(STARTER), "--model", "scripted:noop"]
    assert main([*args, "--resume", str(tmp_path / "nope")]) == 2
    assert "nothing to resume" in capsys.readouterr().err
    assert main([*args, "--resume", str(tmp_path), "--out", str(tmp_path / "other")]) == 2
    assert "drop --out" in capsys.readouterr().err
