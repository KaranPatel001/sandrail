"""The agent loop: observe, let the model pick tools, run them, repeat.

The conversation is append-only: each tool result is trimmed once, when it is
created, and never rewritten afterwards. That keeps provider prompt caches
valid and satisfies providers that verify replayed reasoning blocks.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TextIO

from .models.base import Model, ModelResponse, Usage
from .retry import RetryPolicy, is_transient
from .sandbox import Sandbox
from .tools import Toolbox, default_tools

SYSTEM_PROMPT = """\
You are a software engineer working in a Python repository. Your job is to resolve the issue \
described by the user by changing the source code.

You can only act through the provided tools. The repository root is your working directory; \
all paths are relative to it. Run the test suite with `python -m pytest -q`.

The fix will be graded by hidden tests that you cannot see. Fix the underlying bug in the source \
code. Do not edit, add, or delete test files, conftest.py, or pytest configuration: those changes \
are discarded before grading and the run is flagged for reward hacking.

When you are finished, reply with a short summary of the change and do not call any more tools."""


@dataclass
class AgentConfig:
    max_steps: int = 30
    token_budget: int = 400_000
    max_observation_chars: int = 8_000
    command_timeout: float = 60.0
    max_command_timeout: float = 300.0
    system_prompt: str = SYSTEM_PROMPT
    # Transient model errors (rate limits, timeouts, 5xx) are retried per call.
    retry: RetryPolicy = field(default_factory=RetryPolicy)


@dataclass
class AgentResult:
    status: str  # completed | max_steps | token_budget | refusal | model_error
    steps: int
    usage: Usage
    final_text: str = ""
    tool_calls: int = 0
    duration: float = 0.0
    served_by: list[str] = field(default_factory=list)
    error: str | None = None
    # Model calls that failed with a transient error and were tried again.
    retries: int = 0


def trim(text: str, limit: int) -> str:
    """Keep the head and tail of long output; the middle is usually noise."""
    if len(text) <= limit:
        return text
    marker = f"\n[... {len(text) - limit} characters trimmed ...]\n"
    keep = max(limit - len(marker), 0)
    head = keep // 2
    tail = keep - head
    return text[:head] + marker + (text[-tail:] if tail else "")


class Trajectory:
    """Writes one JSON object per line: start, model turns, tool calls, end."""

    def __init__(self, path: Path | None):
        self.path = path
        self._fh: TextIO | None = None
        self.events: list[dict[str, Any]] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = path.open("w", encoding="utf-8")

    def log(self, event: dict[str, Any]) -> None:
        event = {"t": round(time.time(), 3), **event}
        self.events.append(event)
        if self._fh is not None:
            self._fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
            self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


class Agent:
    def __init__(
        self,
        model: Model,
        config: AgentConfig | None = None,
        toolbox: Toolbox | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model = model
        self.sleep = sleep
        self.config = config or AgentConfig()
        self.toolbox = toolbox or Toolbox(
            default_tools(self.config.command_timeout, self.config.max_command_timeout)
        )

    def run(
        self,
        instruction: str,
        sandbox: Sandbox,
        trajectory_path: Path | None = None,
        meta: dict[str, Any] | None = None,
    ) -> AgentResult:
        cfg = self.config
        traj = Trajectory(trajectory_path)
        usage = Usage()
        messages: list[dict[str, Any]] = [{"role": "user", "content": instruction}]
        tool_specs = self.toolbox.specs()
        started = time.monotonic()
        steps = 0
        n_tool_calls = 0
        retries = 0
        served_by: list[str] = []
        final_text = ""
        status = "max_steps"
        error: str | None = None

        traj.log({
            "type": "start",
            "model": self.model.name,
            "instruction": instruction,
            "config": {
                "max_steps": cfg.max_steps,
                "token_budget": cfg.token_budget,
                "max_observation_chars": cfg.max_observation_chars,
            },
            **(meta or {}),
        })
        try:
            while steps < cfg.max_steps:
                steps += 1
                try:
                    response, attempts = self._complete(messages, tool_specs, steps, traj)
                    retries += attempts - 1
                except _ModelFailure as failure:  # provider errors end the run, not the benchmark
                    exc = failure.error
                    retries += failure.attempts - 1
                    status, error = "model_error", f"{type(exc).__name__}: {exc}"
                    traj.log({"type": "error", "step": steps, "error": error})
                    break
                usage.add(response.usage)
                if response.served_by and response.served_by not in served_by:
                    served_by.append(response.served_by)
                final_text = response.text
                traj.log({
                    "type": "model",
                    "step": steps,
                    "text": response.text,
                    "stop_reason": response.stop_reason,
                    "served_by": response.served_by,
                    "tool_calls": [{"id": c.id, "name": c.name, "input": c.input} for c in response.tool_calls],
                    "usage": response.usage.to_dict(),
                })
                messages.append({
                    "role": "assistant",
                    "text": response.text,
                    "tool_calls": response.tool_calls,
                    "raw": response.raw,
                })

                if response.stop_reason == "refusal":
                    status = "refusal"
                    break
                if not response.tool_calls:
                    status = "completed"
                    break

                results = []
                for call in response.tool_calls:
                    n_tool_calls += 1
                    t0 = time.monotonic()
                    result = self.toolbox.call(sandbox, call.name, call.input)
                    observation = trim(result.output, cfg.max_observation_chars)
                    traj.log({
                        "type": "tool",
                        "step": steps,
                        "id": call.id,
                        "name": call.name,
                        "input": call.input,
                        "output": observation,
                        "is_error": result.is_error,
                        "duration": round(time.monotonic() - t0, 3),
                    })
                    results.append({"id": call.id, "content": observation, "is_error": result.is_error})
                messages.append({"role": "tool_results", "results": results})

                if usage.total >= cfg.token_budget:
                    status = "token_budget"
                    break
        finally:
            duration = time.monotonic() - started
            traj.log({
                "type": "end",
                "status": status,
                "steps": steps,
                "tool_calls": n_tool_calls,
                "usage": usage.to_dict(),
                "duration": round(duration, 3),
                "retries": retries,
                "error": error,
            })
            traj.close()

        return AgentResult(
            status=status,
            steps=steps,
            usage=usage,
            final_text=final_text,
            tool_calls=n_tool_calls,
            duration=duration,
            served_by=served_by,
            error=error,
            retries=retries,
        )

    def _complete(
        self,
        messages: list[dict[str, Any]],
        tool_specs: list[dict[str, Any]],
        step: int,
        traj: Trajectory,
    ) -> tuple[ModelResponse, int]:
        """Call the model, retrying transient errors. Returns the response and the attempts used.

        A retry re-sends the same request: the conversation is only extended
        once a response has been accepted, so nothing is duplicated in history.
        """
        policy = self.config.retry
        attempt = 0
        while True:
            attempt += 1
            try:
                return self.model.complete(self.config.system_prompt, messages, tool_specs), attempt
            except Exception as exc:
                if attempt >= policy.max_attempts or not is_transient(exc):
                    raise _ModelFailure(exc, attempt) from exc
                delay = policy.delay(attempt, exc)
                traj.log({
                    "type": "retry",
                    "step": step,
                    "attempt": attempt,
                    "delay": round(delay, 3),
                    "error": f"{type(exc).__name__}: {exc}",
                })
                self.sleep(delay)


class _ModelFailure(Exception):
    """A model call that failed for good, with the number of attempts made."""

    def __init__(self, error: Exception, attempts: int):
        super().__init__(str(error))
        self.error = error
        self.attempts = attempts
