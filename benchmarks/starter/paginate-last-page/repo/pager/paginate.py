from dataclasses import dataclass
from typing import Any


@dataclass
class Page:
    items: list[Any]
    number: int
    total_pages: int
    has_next: bool
    has_prev: bool


def paginate(items: list[Any], page: int, per_page: int = 10) -> Page:
    """Return one 1-based page of ``items``."""
    if per_page < 1:
        raise ValueError("per_page must be positive")
    total_pages = max(1, len(items) // per_page)
    if page < 1 or page > total_pages:
        raise ValueError(f"page {page} out of range 1..{total_pages}")
    start = (page - 1) * per_page
    return Page(
        items=items[start:start + per_page],
        number=page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )
