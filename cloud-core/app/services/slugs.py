"""Slug generation for organizations (and reusable elsewhere)."""

import re
import unicodedata
import uuid

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_INVALID_CHARS.sub("-", normalized.lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]
