"""Claude adapter tests against a fake client (no network, no API key)."""

from types import SimpleNamespace as NS

from sandrail.agent import Agent
from sandrail.models.base import ToolCall
from sandrail.models.claude import DEFAULT_MODEL, FALLBACK_BETA, ClaudeModel
from sandrail.sandbox import LocalSandbox
from sandrail.tools import Toolbox, default_tools


def usage(i=100, o=20, cr=0, cw=0):
    return NS(input_tokens=i, output_tokens=o, cache_read_input_tokens=cr, cache_creation_input_tokens=cw)


def response(content, stop_reason="tool_use", model=DEFAULT_MODEL, **extra):
    return NS(content=content, stop_reason=stop_reason, usage=usage(), model=model, **extra)


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **params):
        self.calls.append(params)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)
        self.beta = NS(messages=self.messages)


TOOLS = Toolbox(default_tools()).specs()


def test_default_model_and_request_shape():
    client = FakeClient([response([NS(type="text", text="hi")], stop_reason="end_turn")])
    model = ClaudeModel(client=client)
    assert model.name == "claude-opus-5-5"
    model.complete("sys", [{"role": "user", "content": "fix it"}], TOOLS)
    params = client.messages.calls[0]
    assert params["model"] == "claude-opus-5-5"
    assert params["system"] == "sys"
    assert params["tools"] == TOOLS
    assert params["output_config"] == {"effort": "high"}
    assert params["fallbacks"] == "default"
    assert params["betas"] == [FALLBACK_BETA]
    assert params["cache_control"] == {"type": "ephemeral"}
    for forbidden in ("temperature", "top_p", "top_k", "tool_choice", "thinking"):
        assert forbidden not in params


def test_model_is_configurable_and_fallbacks_optional():
    client = FakeClient([response([NS(type="text", text="ok")], stop_reason="end_turn")])
    model = ClaudeModel(model="claude-sonnet-5-5", effort="medium", fallbacks=False, client=client)
    model.complete("s", [{"role": "user", "content": "x"}], TOOLS)
    params = client.messages.calls[0]
    assert params["model"] == "claude-sonnet-5-5"
    assert params["output_config"] == {"effort": "medium"}
    assert "fallbacks" not in params and "betas" not in params


def test_parse_reads_only_text_and_tool_use():
    content = [
        NS(type="thinking", thinking="", signature="sig"),
        NS(type="text", text="Let me look."),
        NS(type="tool_use", id="toolu_1", name="read_file", input={"path": "a.py"}),
        NS(type="fallback", from_=NS(model="x"), to=NS(model="y")),
    ]
    parsed = ClaudeModel.parse(response(content))
    assert parsed.text == "Let me look."
    assert parsed.tool_calls == [ToolCall("toolu_1", "read_file", {"path": "a.py"})]
    assert parsed.stop_reason == "tool_use"
    assert parsed.raw is content
    assert parsed.usage.input_tokens == 100 and parsed.usage.output_tokens == 20


def test_refusal_is_reported_and_no_tools_run():
    content = [NS(type="tool_use", id="t", name="run_command", input={"command": "rm -rf /"})]
    parsed = ClaudeModel.parse(
        response(content, stop_reason="refusal", stop_details=NS(type="refusal", category="cyber", explanation=None))
    )
    assert parsed.stop_reason == "refusal"
    assert parsed.tool_calls == []
    assert "cyber" in parsed.text


def test_history_conversion_replays_raw_blocks():
    raw = [NS(type="thinking", thinking="", signature="s"), NS(type="tool_use", id="t1", name="list_files", input={})]
    messages = [
        {"role": "user", "content": "task"},
        {"role": "assistant", "text": "", "tool_calls": [ToolCall("t1", "list_files", {})], "raw": raw},
        {"role": "tool_results", "results": [{"id": "t1", "content": "a.py", "is_error": False},
                                             {"id": "t2", "content": "", "is_error": True}]},
        {"role": "assistant", "text": "done", "tool_calls": [ToolCall("t3", "read_file", {"path": "a"})], "raw": None},
    ]
    api = ClaudeModel.to_api_messages(messages)
    assert api[0] == {"role": "user", "content": "task"}
    assert api[1] == {"role": "assistant", "content": raw}
    assert api[2]["role"] == "user"
    assert [b["tool_use_id"] for b in api[2]["content"]] == ["t1", "t2"]
    assert api[2]["content"][1]["is_error"] is True
    assert api[2]["content"][1]["content"] == "(empty)"
    assert api[3]["content"] == [
        {"type": "text", "text": "done"},
        {"type": "tool_use", "id": "t3", "name": "read_file", "input": {"path": "a"}},
    ]


def test_full_agent_loop_with_fake_claude(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "x.py").write_text("A = 1\n")
    client = FakeClient([
        response([NS(type="tool_use", id="t1", name="edit_file",
                     input={"path": "x.py", "old_str": "A = 1", "new_str": "A = 2"})]),
        response([NS(type="text", text="Changed A.")], stop_reason="end_turn", model="claude-opus-4-8"),
    ])
    with LocalSandbox(repo) as sb:
        result = Agent(ClaudeModel(client=client)).run("set A to 2", sb)
        assert (sb.workspace / "x.py").read_text() == "A = 2\n"
    assert result.status == "completed"
    assert result.final_text == "Changed A."
    assert result.served_by == ["claude-opus-5-5", "claude-opus-4-8"]
    second = client.messages.calls[1]["messages"]
    assert second[-1]["content"][0]["tool_use_id"] == "t1"
    assert second[-1]["content"][0]["content"] == "edited x.py"
