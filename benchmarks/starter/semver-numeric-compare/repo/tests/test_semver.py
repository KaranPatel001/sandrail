import pytest

from versions import compare, parse


def test_patch_order():
    assert compare("1.2.3", "1.2.4") == -1


def test_equal():
    assert compare("2.0.0", "v2.0.0") == 0


def test_rejects_garbage():
    with pytest.raises(ValueError):
        parse("1.2")
