"""A deterministic model that replays a fixed script of tool calls.

Used by the test suite and by the built-in ``scripted:reference`` and
``scripted:cheat`` baselines. Token usage is estimated from character counts
(about four characters per token) so budget logic can be exercised offline.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Union

from .base import Model, ModelResponse, ToolCall, Usage

# A step is either a list of {"tool": name, "input": {...}} dicts, a final
# text string (ends the run), or a callable that receives the conversation and
# returns one of those two.
Step = Union[str, list[dict[str, Any]], Callable[[list[dict[str, Any]]], Union[str, list[dict[str, Any]]]]]


def _estimate_tokens(obj: Any) -> int:
    return max(1, len(json.dumps(obj, default=str)) // 4)


class ScriptedModel(Model):
    def __init__(self, steps: list[Step], name: str = "scripted", final_text: str = "Done."):
        self.steps = list(steps)
        self.name = name
        self.final_text = final_text
        self.calls = 0
        self.seen_messages: list[list[dict[str, Any]]] = []

    def complete(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        self.seen_messages.append(list(messages))
        index = self.calls
        self.calls += 1
        step: Any = self.steps[index] if index < len(self.steps) else self.final_text
        if callable(step):
            step = step(messages)

        input_tokens = _estimate_tokens([system, tools, _plain(messages)])
        if isinstance(step, str):
            return ModelResponse(
                text=step,
                usage=Usage(input_tokens=input_tokens, output_tokens=_estimate_tokens(step)),
                stop_reason="end_turn",
                served_by=self.name,
            )
        calls = [
            ToolCall(id=f"call_{index}_{i}", name=item["tool"], input=dict(item.get("input", {})))
            for i, item in enumerate(step)
        ]
        return ModelResponse(
            text="",
            tool_calls=calls,
            usage=Usage(input_tokens=input_tokens, output_tokens=_estimate_tokens(step)),
            stop_reason="tool_use",
            served_by=self.name,
        )


def _plain(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        m = {k: v for k, v in m.items() if k != "raw"}
        if "tool_calls" in m:
            m["tool_calls"] = [vars(c) for c in m["tool_calls"]]
        out.append(m)
    return out
