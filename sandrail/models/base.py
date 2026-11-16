"""Provider-neutral model interface.

The agent keeps the conversation as a list of plain dicts:

* ``{"role": "user", "content": str}``
* ``{"role": "assistant", "text": str, "tool_calls": [ToolCall, ...], "raw": Any}``
* ``{"role": "tool_results", "results": [{"id", "content", "is_error"}, ...]}``

``raw`` is whatever the adapter returned in ``ModelResponse.raw``. Adapters
that need the provider's exact blocks back (Claude's thinking blocks must be
replayed unchanged) read it; the agent never inspects it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_write_tokens

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


@dataclass
class ModelResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    # "tool_use", "end_turn", "max_tokens", "refusal", ...
    stop_reason: str = "end_turn"
    raw: Any = None
    # The model that actually served the turn (may differ after a fallback).
    served_by: str | None = None


class Model(ABC):
    """One model endpoint. ``name`` is used for reports and cost lookup."""

    name: str = "model"

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        """Return the model's next turn given the conversation so far."""
