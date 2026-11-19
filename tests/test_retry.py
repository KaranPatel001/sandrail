"""Retrying transient model errors: classification, backoff, and the agent loop."""

import json
from types import SimpleNamespace as NS

import pytest

from sandrail.agent import Agent, AgentConfig
from sandrail.models.base import Model
from sandrail.models.scripted import ScriptedModel
from sandrail.retry import RetryPolicy, is_transient, retry_after_seconds
from sandrail.sandbox import LocalSandbox


class StatusError(Exception):
    def __init__(self, status_code, headers=None):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.response = NS(headers=headers or {})


class APIConnectionError(Exception):
    """Same name as the SDK class; carries no status code."""


class FlakyModel(Model):
    """Raises the queued errors, one per call, then behaves like the wrapped model."""

    def __init__(self, errors, inner):
        self.errors = list(errors)
        self.inner = inner
        self.name = inner.name
        self.attempts = 0

    def complete(self, system, messages, tools):
        self.attempts += 1
        if self.errors:
            raise self.errors.pop(0)
        return self.inner.complete(system, messages, tools)


def make_sb(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_bytes(b"alpha\n")
    return LocalSandbox(repo)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504, 529])
def test_retryable_statuses(status):
    assert is_transient(StatusError(status))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
def test_client_errors_are_not_retried(status):
    assert not is_transient(StatusError(status))


def test_connection_and_timeout_errors_are_transient():
    assert is_transient(TimeoutError("slow"))
    assert is_transient(ConnectionResetError("reset"))
    assert is_transient(APIConnectionError("no route"))
    assert not is_transient(ValueError("bad input"))
    assert not is_transient(KeyError("x"))


def test_classification_follows_the_cause_chain():
    try:
        try:
            raise ConnectionResetError("reset")
        except ConnectionResetError as inner:
            raise RuntimeError("request failed") from inner
    except RuntimeError as wrapped:
        assert is_transient(wrapped)


def test_http_status_outranks_a_transient_looking_cause():
    # A 400 that happens to wrap a timeout is still a bad request.
    try:
        try:
            raise TimeoutError("slow")
        except TimeoutError as inner:
            raise StatusError(400) from inner
    except StatusError as err:
        assert not is_transient(err)


def test_backoff_grows_and_is_capped():
    policy = RetryPolicy(max_attempts=5, base_delay=1.0, max_delay=30.0)
    low = [policy.delay(n, rand=lambda: 0.0) for n in range(1, 8)]
    high = [policy.delay(n, rand=lambda: 1.0) for n in range(1, 8)]
    assert low == [0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 15.0]
    assert high == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
    assert all(wait > 0 for wait in low)  # never an immediate retry


def test_retry_after_raises_the_wait_up_to_the_cap():
    policy = RetryPolicy()
    assert retry_after_seconds(StatusError(429, {"retry-after": "7"})) == 7.0
    assert retry_after_seconds(StatusError(429, {"retry-after": "soon"})) is None
    assert retry_after_seconds(StatusError(429)) is None
    assert policy.delay(1, StatusError(429, {"retry-after": "7"}), rand=lambda: 0.0) == 7.0
    assert policy.delay(1, StatusError(429, {"retry-after": "600"}), rand=lambda: 0.0) == 30.0


def test_agent_retries_transient_errors_and_finishes(tmp_path):
    inner = ScriptedModel([[{"tool": "read_file", "input": {"path": "a.txt"}}], "Done."])
    model = FlakyModel([StatusError(429), StatusError(529)], inner)
    sleeps = []
    traj = tmp_path / "traj.jsonl"
    with make_sb(tmp_path) as sb:
        result = Agent(model, sleep=sleeps.append).run("do it", sb, traj)

    assert result.status == "completed"
    assert result.steps == 2  # retries do not consume steps
    assert result.retries == 2
    assert len(sleeps) == 2 and all(wait > 0 for wait in sleeps)
    assert model.attempts == 4

    events = read_jsonl(traj)
    assert [e["type"] for e in events] == ["start", "retry", "retry", "model", "tool", "model", "end"]
    assert events[1]["attempt"] == 1 and events[2]["attempt"] == 2
    assert events[-1]["retries"] == 2
    # A retry re-sends the same request; nothing is added to the conversation.
    assert len(inner.seen_messages[0]) == 1


def test_agent_gives_up_after_max_attempts(tmp_path):
    model = FlakyModel([StatusError(503)] * 10, ScriptedModel(["never reached"]))
    sleeps = []
    config = AgentConfig(retry=RetryPolicy(max_attempts=3))
    with make_sb(tmp_path) as sb:
        result = Agent(model, config, sleep=sleeps.append).run("do it", sb)

    assert result.status == "model_error"
    assert "HTTP 503" in result.error
    assert model.attempts == 3
    assert len(sleeps) == 2
    assert result.retries == 2


def test_agent_does_not_retry_fatal_errors(tmp_path):
    model = FlakyModel([StatusError(401)], ScriptedModel(["never reached"]))
    sleeps = []
    with make_sb(tmp_path) as sb:
        result = Agent(model, sleep=sleeps.append).run("do it", sb)

    assert result.status == "model_error"
    assert model.attempts == 1
    assert sleeps == []
    assert result.retries == 0


def test_attempt_budget_is_per_model_call(tmp_path):
    # Two failures before each of two turns: four in total, more than one call may use.
    inner = ScriptedModel([[{"tool": "list_files", "input": {}}], "Done."])

    class FailsTwicePerTurn(Model):
        name = "flaky"

        def __init__(self):
            self.failures_left = 2

        def complete(self, system, messages, tools):
            if self.failures_left:
                self.failures_left -= 1
                raise StatusError(500)
            self.failures_left = 2
            return inner.complete(system, messages, tools)

    config = AgentConfig(retry=RetryPolicy(max_attempts=3))
    with make_sb(tmp_path) as sb:
        result = Agent(FailsTwicePerTurn(), config, sleep=lambda _: None).run("do it", sb)

    assert result.status == "completed"
    assert result.retries == 4
