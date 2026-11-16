import json

from sandrail.agent import Agent, AgentConfig, trim
from sandrail.models.base import Model, ModelResponse, Usage
from sandrail.models.scripted import ScriptedModel
from sandrail.sandbox import LocalSandbox


def make_sb(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_bytes(b"alpha\n")
    return LocalSandbox(repo)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_trim():
    assert trim("short", 100) == "short"
    text = "A" * 500 + "B" * 500
    out = trim(text, 200)
    assert len(out) <= 200
    assert out.startswith("A") and out.endswith("B")
    assert "characters trimmed" in out


def test_loop_runs_tools_and_records_trajectory(tmp_path):
    model = ScriptedModel([
        [{"tool": "read_file", "input": {"path": "a.txt"}}],
        [{"tool": "write_file", "input": {"path": "b.txt", "content": "beta\n"}},
         {"tool": "list_files", "input": {}}],
        "All done.",
    ])
    traj = tmp_path / "out" / "traj.jsonl"
    with make_sb(tmp_path) as sb:
        result = Agent(model).run("do it", sb, traj, meta={"task_id": "t1"})
        assert (sb.workspace / "b.txt").read_text() == "beta\n"

    assert result.status == "completed"
    assert result.steps == 3
    assert result.tool_calls == 3
    assert result.final_text == "All done."
    assert result.usage.total > 0

    events = read_jsonl(traj)
    assert [e["type"] for e in events] == ["start", "model", "tool", "model", "tool", "tool", "model", "end"]
    assert events[0]["task_id"] == "t1"
    assert events[2]["output"] == "alpha\n"
    assert events[-1]["status"] == "completed"

    # Tool results are fed back to the model in the next turn.
    second_call = model.seen_messages[1]
    assert second_call[-1]["role"] == "tool_results"
    assert second_call[-1]["results"][0]["content"] == "alpha\n"


def test_history_is_append_only(tmp_path):
    model = ScriptedModel([[{"tool": "list_files", "input": {}}]] * 3)
    with make_sb(tmp_path) as sb:
        Agent(model, AgentConfig(max_steps=4)).run("go", sb)
    for earlier, later in zip(model.seen_messages, model.seen_messages[1:]):
        assert later[: len(earlier)] == earlier


def test_max_steps(tmp_path):
    model = ScriptedModel([[{"tool": "list_files", "input": {}}]] * 10)
    with make_sb(tmp_path) as sb:
        result = Agent(model, AgentConfig(max_steps=3)).run("loop", sb)
    assert result.status == "max_steps"
    assert result.steps == 3


def test_token_budget(tmp_path):
    model = ScriptedModel([[{"tool": "list_files", "input": {}}]] * 10)
    with make_sb(tmp_path) as sb:
        result = Agent(model, AgentConfig(max_steps=10, token_budget=1)).run("loop", sb)
    assert result.status == "token_budget"
    assert result.steps == 1


def test_observations_are_trimmed(tmp_path):
    model = ScriptedModel([[{"tool": "write_file", "input": {"path": "big.txt", "content": "x" * 5000}}],
                           [{"tool": "read_file", "input": {"path": "big.txt"}}]])
    traj = tmp_path / "t.jsonl"
    with make_sb(tmp_path) as sb:
        Agent(model, AgentConfig(max_observation_chars=300)).run("read", sb, traj)
    tool_events = [e for e in read_jsonl(traj) if e["type"] == "tool"]
    assert len(tool_events[1]["output"]) <= 300
    assert model.seen_messages[2][-1]["results"][0]["content"] == tool_events[1]["output"]


def test_tool_errors_are_returned_to_model(tmp_path):
    model = ScriptedModel([[{"tool": "read_file", "input": {"path": "../../etc/passwd"}}], "ok"])
    with make_sb(tmp_path) as sb:
        result = Agent(model).run("x", sb)
    assert result.status == "completed"
    assert model.seen_messages[1][-1]["results"][0]["is_error"] is True


class RefusingModel(Model):
    name = "refuser"

    def complete(self, system, messages, tools):
        return ModelResponse(text="[refusal]", stop_reason="refusal", usage=Usage(10, 1))


class BrokenModel(Model):
    name = "broken"

    def complete(self, system, messages, tools):
        raise RuntimeError("503 overloaded")


def test_refusal_ends_run(tmp_path):
    with make_sb(tmp_path) as sb:
        result = Agent(RefusingModel()).run("x", sb)
    assert result.status == "refusal"
    assert result.steps == 1


def test_model_error_ends_run(tmp_path):
    traj = tmp_path / "t.jsonl"
    with make_sb(tmp_path) as sb:
        result = Agent(BrokenModel()).run("x", sb, traj)
    assert result.status == "model_error"
    assert "overloaded" in result.error
    assert read_jsonl(traj)[-1]["status"] == "model_error"


def test_scripted_callable_step(tmp_path):
    def decide(messages):
        last = messages[-1]
        if last["role"] == "tool_results" and "a.txt" in last["results"][0]["content"]:
            return "saw a.txt"
        return [{"tool": "list_files", "input": {}}]

    model = ScriptedModel([decide, decide])
    with make_sb(tmp_path) as sb:
        result = Agent(model).run("x", sb)
    assert result.final_text == "saw a.txt"
