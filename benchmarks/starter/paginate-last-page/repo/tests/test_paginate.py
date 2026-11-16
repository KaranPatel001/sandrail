import pytest

from pager import paginate


def test_exact_multiple():
    page = paginate(list(range(20)), page=2, per_page=10)
    assert page.items == list(range(10, 20))
    assert page.total_pages == 2
    assert not page.has_next


def test_invalid_per_page():
    with pytest.raises(ValueError):
        paginate([1, 2], page=1, per_page=0)
