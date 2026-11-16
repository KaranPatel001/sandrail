from shop import Cart, to_cents


def test_float_prices():
    assert to_cents(19.99) == 1999
    assert to_cents(0.29) == 29
    assert to_cents(4.35) == 435


def test_half_cent_rounds_up():
    assert to_cents(1.005) == 101


def test_cart_subtotal():
    cart = Cart()
    cart.add("book", 19.99, 3)
    cart.add("pen", 0.29, 10)
    assert cart.subtotal_cents() == 5997 + 290


def test_cart_discount():
    cart = Cart()
    cart.add("book", 19.99, 1)
    assert cart.total_cents(10) == 1999 - 199
