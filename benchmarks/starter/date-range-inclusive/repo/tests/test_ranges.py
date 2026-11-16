from datetime import date

import pytest

from calendarx import iter_days


def test_starts_at_start():
    days = list(iter_days(date(2024, 1, 1), date(2024, 1, 10)))
    assert days[0] == date(2024, 1, 1)


def test_bad_step():
    with pytest.raises(ValueError):
        list(iter_days(date(2024, 1, 1), date(2024, 1, 2), step=0))


def test_empty_when_end_before_start():
    assert list(iter_days(date(2024, 1, 5), date(2024, 1, 1))) == []
