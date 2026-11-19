"""Retry policy for model calls.

A benchmark should measure the model, not the network. A rate limit or a
dropped connection is retried with backoff; anything else ends the run as
``model_error`` straight away, because retrying a bad request or an exhausted
quota only burns time.

Errors are classified from structure (HTTP status, exception type), never from
the text of the message.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

# Request timeout, conflict/lock, rate limit, server errors, and 529 (overloaded).
TRANSIENT_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 529})

# SDK exception classes that carry no HTTP status. Matched by name so this
# module does not import any provider SDK.
TRANSIENT_ERROR_NAMES = frozenset({"APIConnectionError", "APITimeoutError"})


def _chain(exc: BaseException):
    """The exception and everything it was raised from, each visited once."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def is_transient(exc: BaseException) -> bool:
    """Whether retrying the same request could plausibly succeed."""
    for err in _chain(exc):
        status = getattr(err, "status_code", None)
        if isinstance(status, int):
            # An HTTP answer decides the matter: 429 retries, 400/401/403 do not.
            return status in TRANSIENT_STATUS
        if isinstance(err, (TimeoutError, ConnectionError)):
            return True
        if type(err).__name__ in TRANSIENT_ERROR_NAMES:
            return True
    return False


def retry_after_seconds(exc: BaseException) -> float | None:
    """The server's ``Retry-After`` hint in seconds, when it sent a usable one."""
    for err in _chain(exc):
        headers = getattr(getattr(err, "response", None), "headers", None)
        if headers is None:
            continue
        try:
            value = float(headers.get("retry-after"))
        except (TypeError, ValueError, AttributeError):
            continue
        if value >= 0:
            return value
    return None


@dataclass(frozen=True)
class RetryPolicy:
    """Up to ``max_attempts`` tries per model call, with exponential backoff.

    The wait before retry ``n`` is drawn from the upper half of
    ``min(max_delay, base_delay * 2**(n-1))`` ("equal jitter"), so parallel
    runs spread out but no retry fires immediately. A ``Retry-After`` hint
    from the server raises the wait, up to ``max_delay``.
    """

    max_attempts: int = 5
    base_delay: float = 1.0
    max_delay: float = 30.0

    def delay(self, attempt: int, exc: BaseException | None = None, rand: Callable[[], float] = random.random) -> float:
        """Seconds to wait after failed attempt number ``attempt`` (1-based)."""
        cap = min(self.max_delay, self.base_delay * 2 ** (attempt - 1))
        wait = cap / 2 + rand() * cap / 2
        hint = retry_after_seconds(exc) if exc is not None else None
        if hint is not None:
            wait = max(wait, min(hint, self.max_delay))
        return wait
