"""Claude adapter using the official ``anthropic`` SDK with client tool use.

Notes on the request shape (current Claude models):

* No ``temperature``/``top_p``: sampling parameters are rejected.
* No forced ``tool_choice``: ``any``/``tool`` return 400 on Opus 5.5, so the
  default ``auto`` is used and the system prompt steers tool use.
* Thinking is left at its default (adaptive); depth is set with
  ``output_config.effort``. Assistant turns are replayed exactly as returned
  (thinking blocks included), and the history is append-only.
* Server-side refusal fallback is on by default (``fallbacks="default"``).
  If the whole chain still refuses, ``stop_reason == "refusal"`` ends the run.
* Only ``text`` and ``tool_use`` blocks are read; every other block type is
  carried in ``raw`` and echoed back untouched.
"""

from __future__ import annotations

from typing import Any

from .base import Model, ModelResponse, ToolCall, Usage

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeModel(Model):
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 16_000,
        effort: str | None = "high",
        fallbacks: bool = True,
        prompt_caching: bool = True,
        client: Any = None,
    ):
        self.name = model
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.fallbacks = fallbacks
        self.prompt_caching = prompt_caching
        if client is None:
            import anthropic  # imported lazily so the package works without the extra

            # The agent loop owns retries (see sandrail/retry.py). Leaving the SDK's
            # own retries on would multiply the two attempt counts.
            client = anthropic.Anthropic(max_retries=0)
        self.client = client

    # -- request building -------------------------------------------------

    @staticmethod
    def to_api_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            role = m["role"]
            if role == "user":
                out.append({"role": "user", "content": m["content"]})
            elif role == "assistant":
                if m.get("raw") is not None:
                    content = m["raw"]
                else:
                    content = []
                    if m.get("text"):
                        content.append({"type": "text", "text": m["text"]})
                    for c in m.get("tool_calls", []):
                        content.append({"type": "tool_use", "id": c.id, "name": c.name, "input": c.input})
                out.append({"role": "assistant", "content": content})
            elif role == "tool_results":
                # All results for one assistant turn go back in a single user message.
                out.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": r["id"],
                            "content": r["content"] or "(empty)",
                            "is_error": bool(r.get("is_error")),
                        }
                        for r in m["results"]
                    ],
                })
            else:
                raise ValueError(f"unknown message role: {role!r}")
        return out

    def request_params(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "tools": tools,
            "messages": self.to_api_messages(messages),
        }
        if self.effort:
            params["output_config"] = {"effort": self.effort}
        if self.prompt_caching:
            params["cache_control"] = {"type": "ephemeral"}
        if self.fallbacks:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    # -- call ---------------------------------------------------------------

    def complete(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        params = self.request_params(system, messages, tools)
        if self.fallbacks:
            response = self.client.beta.messages.create(**params)
        else:
            response = self.client.messages.create(**params)
        return self.parse(response)

    @staticmethod
    def parse(response: Any) -> ModelResponse:
        usage = Usage(
            input_tokens=getattr(response.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(response.usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        )
        stop_reason = response.stop_reason or "end_turn"
        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            return ModelResponse(
                text=f"[refusal: {category or 'unspecified'}]",
                usage=usage,
                stop_reason="refusal",
                raw=response.content,
                served_by=getattr(response, "model", None),
            )

        texts: list[str] = []
        calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                texts.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input or {})))
        return ModelResponse(
            text="\n".join(texts),
            tool_calls=calls,
            usage=usage,
            stop_reason=stop_reason,
            raw=response.content,
            served_by=getattr(response, "model", None),
        )
