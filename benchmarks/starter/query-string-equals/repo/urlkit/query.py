from urllib.parse import unquote


def parse_query(qs: str) -> dict[str, list[str]]:
    """Parse a URL query string into ``{key: [values...]}``.

    ``+`` decodes to a space, values are percent-decoded, a key with no ``=``
    gets an empty value, and repeated keys keep every value in order.
    """
    result: dict[str, list[str]] = {}
    if qs.startswith("?"):
        qs = qs[1:]
    for pair in qs.split("&"):
        if not pair:
            continue
        parts = pair.split("=")
        key = parts[0]
        value = parts[1] if len(parts) > 1 else ""
        key = unquote(key.replace("+", " "))
        value = unquote(value.replace("+", " "))
        result.setdefault(key, []).append(value)
    return result
