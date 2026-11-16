from spans import merge_intervals, total_covered


def test_touching_merge():
    assert merge_intervals([(1, 2), (2, 3)]) == [(1, 3)]


def test_unsorted_chain():
    assert merge_intervals([(5, 6), (1, 2), (2, 5)]) == [(1, 6)]


def test_nested():
    assert merge_intervals([(1, 10), (2, 3), (10, 12)]) == [(1, 12)]


def test_total_covered_counts_once():
    assert total_covered([(0, 5), (5, 10), (3, 4)]) == 10
