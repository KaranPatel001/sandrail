from shop import Cart, to_cents


def test_round_numbers():
    assert to_cents(2.5) == 250
    assert to_cents(10) == 1000


def test_cart_quantities_accumulate():
    cart = Cart()
    cart.add("tea", 4.0, 2)
    cart.add("tea", 4.0)
    assert cart.subtotal_cents() == 1200
