import pytest

from pager import paginate


def test_partial_last_page():
    page = paginate(list(range(25)), page=3, per_page=10)
    assert page.items == [20, 21, 22, 23, 24]
    assert page.total_pages == 3
    assert page.has_prev and not page.has_next


def test_middle_page_has_next():
    page = paginate(list(range(25)), page=2, per_page=10)
    assert page.has_next


def test_empty_list_has_one_page():
    page = paginate([], page=1, per_page=10)
    assert page.items == []
    assert page.total_pages == 1


def test_fewer_items_than_page():
    assert paginate([1, 2, 3], page=1, per_page=10).total_pages == 1


def test_out_of_range_still_rejected():
    with pytest.raises(ValueError):
        paginate(list(range(25)), page=4, per_page=10)
