from spans import merge_intervals


def test_overlap():
    assert merge_intervals([(1, 3), (2, 5)]) == [(1, 5)]


def test_disjoint():
    assert merge_intervals([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]


def test_empty():
    assert merge_intervals([]) == []
