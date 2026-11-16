from sandrail.cli import main
from sandrail.models.base import Usage
from sandrail.pricing import estimate_cost
from sandrail.report import render_report, summarize
from sandrail.runner import RunRecord

from .conftest import STARTER


def record(task="t", run=1, passed=True, flagged=False, model="claude-opus-5-5", cost=0.01, steps=4):
    return RunRecord(
        task_id=task, run=run, model=model, status="completed", steps=steps, tool_calls=steps,
        usage={"input_tokens": 1000, "output_tokens": 100, "cache_read_tokens": 0, "cache_write_tokens": 0},
        cost_usd=cost, duration=1.0, passed=passed, flagged=flagged,
        flags=[{"path": "conftest.py", "change": "added", "reason": "r"}] if flagged else [],
        tests_passed=1, tests_failed=0, applied=[], discarded=[], trajectory="t.jsonl",
    )


def test_estimate_cost():
    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert estimate_cost("claude-opus-5-5", u) == 24.0
    assert estimate_cost("scripted:reference", u) == 0.0
    assert estimate_cost("some-unknown-model", u) is None
    cached = Usage(cache_read_tokens=1_000_000)
    assert estimate_cost("claude-opus-5-5", cached) == 0.20


def test_summary_counts_flagged_passes_as_not_clean():
    recs = [record("a", passed=True), record("a", 2, passed=False), record("b", passed=True, flagged=True)]
    s = summarize(recs)
    assert s["runs"] == 3
    assert s["clean_passed"] == 1
    assert s["passed"] == 2
    assert s["flagged"] == 1
    assert s["tasks_solved_any"] == 1
    assert s["tasks_solved_all"] == 0
    assert round(s["cost_usd"], 4) == 0.03


def test_report_shows_unknown_cost_as_na():
    text = render_report([record(cost=None)], "mystery", "x", 1)
    assert "| Estimated cost | n/a |" in text


def test_cli_run_reference_single_task(tmp_path, capsys):
    code = main(["run", "--tasks", str(STARTER), "--model", "scripted:reference",
                 "--task", "query-string-equals", "--out", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "PASS  query-string-equals run 1" in out
    assert (tmp_path / "results.jsonl").is_file()
    assert (tmp_path / "report.md").is_file()


def test_cli_run_cheat_prints_flag(tmp_path, capsys):
    main(["run", "--tasks", str(STARTER), "--model", "scripted:cheat", "--task", "lru-get-recency", "--out", str(tmp_path)])
    assert "FAIL [FLAGGED]  lru-get-recency" in capsys.readouterr().out


def test_cli_list_and_validate(capsys):
    assert main(["list", "--tasks", str(STARTER)]) == 0
    assert "token-bucket-cap" in capsys.readouterr().out
    assert main(["validate", "--tasks", str(STARTER), "--task", "token-bucket-cap"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_rejects_zero_runs():
    assert main(["run", "--model", "scripted:noop", "--runs", "0"]) == 2


def test_default_tasks_dir_prefers_local_checkout(tmp_path, monkeypatch):
    from sandrail.task import default_tasks_dir, load_tasks

    (tmp_path / "benchmarks" / "starter").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert default_tasks_dir().as_posix() == "benchmarks/starter"

    # Without a local copy, the bundled starter set is used.
    monkeypatch.chdir(tmp_path / "benchmarks")
    assert len(load_tasks(default_tasks_dir())) == 12
