import re
import unicodedata


def slugify(text: str, sep: str = "-") -> str:
    """Convert text to a URL slug.

    Accents are stripped, letters are lowercased, and every run of characters
    that are not ASCII letters or digits becomes a single ``sep``. The slug
    never starts or ends with ``sep``.
    """
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    slug = re.sub(r"[^a-z0-9]", sep, lowered)
    return slug.strip(sep)
