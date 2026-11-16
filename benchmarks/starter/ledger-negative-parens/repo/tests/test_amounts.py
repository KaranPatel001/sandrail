from decimal import Decimal

import pytest

from ledger import parse_amount, total_by_category


def test_plain_and_thousands():
    assert parse_amount("$1,234.50") == Decimal("1234.50")


def test_leading_minus():
    assert parse_amount("-3.00") == Decimal("-3.00")


def test_garbage_rejected():
    with pytest.raises(ValueError):
        parse_amount("twelve")


def test_totals_positive_only():
    assert total_by_category([("food", "10.00"), ("food", "2.50")]) == {"food": Decimal("12.50")}
