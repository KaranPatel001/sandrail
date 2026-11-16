"""Estimated per-token prices in USD per million tokens.

These are list prices for the first-party Claude API at the time of writing
and are used only for the "estimated cost" column of reports. Check the
provider's pricing page before relying on them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models.base import Usage


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float  # 5-minute cache writes, 1.25x input


def _p(inp: float, out: float, cache_read: float) -> Price:
    return Price(inp, out, cache_read, inp * 1.25)


PRICES: dict[str, Price] = {
    "claude-fable-5-2": _p(8.0, 40.0, 0.20),
    "claude-opus-5-5": _p(4.0, 20.0, 0.20),
    "claude-opus-5": _p(5.0, 25.0, 0.50),
    "claude-opus-4-8": _p(5.0, 25.0, 0.50),
    "claude-sonnet-5-5": _p(2.0, 10.0, 0.10),
    "claude-sonnet-5": _p(2.0, 10.0, 0.20),
    "claude-haiku-5-5": _p(0.10, 0.50, 0.01),
}


def estimate_cost(model: str, usage: Usage) -> float | None:
    """Return the estimated USD cost, 0.0 for scripted models, None if unknown."""
    if model.startswith("scripted"):
        return 0.0
    price = PRICES.get(model)
    if price is None:
        return None
    return (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    ) / 1_000_000
