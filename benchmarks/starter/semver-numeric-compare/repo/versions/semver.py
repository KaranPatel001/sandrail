def parse(version: str) -> tuple:
    """Parse ``MAJOR.MINOR.PATCH`` (optional leading ``v``, ``-suffix`` ignored)."""
    core = version.strip().removeprefix("v").split("-", 1)[0]
    parts = core.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not a version: {version!r}")
    return tuple(parts)


def compare(a: str, b: str) -> int:
    """Return -1, 0 or 1 as ``a`` is older than, equal to, or newer than ``b``."""
    pa, pb = parse(a), parse(b)
    return (pa > pb) - (pa < pb)


def latest(versions: list[str]) -> str:
    """The newest version in ``versions``."""
    if not versions:
        raise ValueError("no versions given")
    return max(versions, key=parse)
