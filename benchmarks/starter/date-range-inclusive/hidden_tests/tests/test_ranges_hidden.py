from datetime import date

from calendarx import count_weekdays, iter_days


def test_end_included():
    assert list(iter_days(date(2024, 3, 1), date(2024, 3, 3))) == [
        date(2024, 3, 1), date(2024, 3, 2), date(2024, 3, 3)
    ]


def test_single_day():
    assert list(iter_days(date(2024, 3, 1), date(2024, 3, 1))) == [date(2024, 3, 1)]


def test_step_lands_on_end():
    assert list(iter_days(date(2024, 3, 1), date(2024, 3, 7), step=3)) == [
        date(2024, 3, 1), date(2024, 3, 4), date(2024, 3, 7)
    ]


def test_full_week_weekdays():
    # 2024-03-04 is a Monday, 2024-03-10 a Sunday.
    assert count_weekdays(date(2024, 3, 4), date(2024, 3, 10)) == 5


def test_friday_counts():
    assert count_weekdays(date(2024, 3, 4), date(2024, 3, 8)) == 5
