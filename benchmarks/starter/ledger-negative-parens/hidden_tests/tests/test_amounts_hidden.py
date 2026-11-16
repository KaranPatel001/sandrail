from decimal import Decimal

import pytest

from ledger import parse_amount, total_by_category


def test_parentheses_are_negative():
    assert parse_amount("(12.50)") == Decimal("-12.50")


def test_dollar_and_parentheses():
    assert parse_amount("$(1,200.00)") == Decimal("-1200.00")


def test_minus_still_works():
    assert parse_amount("-7") == Decimal("-7")


def test_refund_reduces_total():
    rows = [("travel", "$300.00"), ("travel", "(45.00)"), ("food", "12.00")]
    assert total_by_category(rows) == {"travel": Decimal("255.00"), "food": Decimal("12.00")}


def test_unbalanced_parenthesis_rejected():
    with pytest.raises(ValueError):
        parse_amount("(12.00")
