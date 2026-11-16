def to_cents(amount: float) -> int:
    """Convert a dollar amount to integer cents, rounding to the nearest cent (half up)."""
    return int(amount * 100)


class Cart:
    def __init__(self) -> None:
        self.lines: dict[str, tuple[float, int]] = {}

    def add(self, sku: str, price: float, quantity: int = 1) -> None:
        if quantity < 1:
            raise ValueError("quantity must be at least 1")
        _, existing = self.lines.get(sku, (price, 0))
        self.lines[sku] = (price, existing + quantity)

    def subtotal_cents(self) -> int:
        return sum(to_cents(price) * qty for price, qty in self.lines.values())

    def total_cents(self, discount_percent: int = 0) -> int:
        """Subtotal minus a whole-percent discount (discount rounded down)."""
        if not 0 <= discount_percent <= 100:
            raise ValueError("discount_percent must be between 0 and 100")
        subtotal = self.subtotal_cents()
        return subtotal - subtotal * discount_percent // 100
