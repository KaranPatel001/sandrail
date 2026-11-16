def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping closed intervals ``[start, end]``.

    Intervals that share an endpoint overlap. The result is sorted and
    disjoint.
    """
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def total_covered(intervals: list[tuple[int, int]]) -> int:
    """Total length covered by the intervals, counting overlaps once."""
    return sum(end - start for start, end in merge_intervals(intervals))
