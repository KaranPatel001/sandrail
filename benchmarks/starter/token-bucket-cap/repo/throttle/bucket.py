import time
from typing import Callable


class TokenBucket:
    """Token-bucket rate limiter.

    Holds at most ``capacity`` tokens and gains ``refill_rate`` tokens per
    second. ``clock`` returns seconds and is injectable for tests.
    """

    def __init__(self, capacity: int, refill_rate: float, clock: Callable[[], float] = time.monotonic):
        if capacity < 1 or refill_rate <= 0:
            raise ValueError("capacity and refill_rate must be positive")
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.clock = clock
        self.tokens = float(capacity)
        self.updated = clock()

    def _refill(self) -> None:
        now = self.clock()
        elapsed = max(0.0, now - self.updated)
        self.tokens = self.tokens + elapsed * self.refill_rate
        self.updated = now

    def try_acquire(self, n: int = 1) -> bool:
        """Take ``n`` tokens if available. Returns whether it succeeded."""
        if n > self.capacity:
            raise ValueError("cannot acquire more than capacity")
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False
