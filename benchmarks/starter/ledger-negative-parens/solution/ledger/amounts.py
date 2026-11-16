from decimal import Decimal, InvalidOperation
from typing import Iterable


def parse_amount(text: str) -> Decimal:
    """Parse a money amount such as ``"$1,234.50"``, ``"-3"`` or ``"(12.00)"``.

    Parentheses denote a negative amount (accounting notation). A ``$`` sign
    and thousands separators are ignored.
    """
    s = text.strip().replace("$", "")
    negative = False
    if s.startswith("-"):
        negative = True
        s = s[1:]
    if s.startswith("(") and s.endswith(")"):
        negative = not negative
        s = s[1:-1]
    s = s.replace(",", "")
    try:
        value = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"not an amount: {text!r}") from None
    return -value if negative else value


def total_by_category(rows: Iterable[tuple[str, str]]) -> dict[str, Decimal]:
    """Sum ``(category, amount_text)`` rows per category."""
    totals: dict[str, Decimal] = {}
    for category, amount in rows:
        totals[category] = totals.get(category, Decimal("0")) + parse_amount(amount)
    return totals
