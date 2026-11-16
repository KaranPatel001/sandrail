from datetime import date, timedelta
from typing import Iterator


def iter_days(start: date, end: date, step: int = 1) -> Iterator[date]:
    """Yield dates from ``start`` to ``end`` inclusive, ``step`` days apart."""
    if step < 1:
        raise ValueError("step must be at least 1")
    current = start
    while current <= end:
        yield current
        current += timedelta(days=step)


def count_weekdays(start: date, end: date) -> int:
    """Number of Monday-Friday dates between ``start`` and ``end`` inclusive."""
    return sum(1 for day in iter_days(start, end) if day.weekday() < 5)
