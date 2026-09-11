"""Narrow citation syntax shared by extraction and edition-aware resolvers."""

from __future__ import annotations

import re

MULTI_LETTER_OBJECT_COORDINATE = r"[A-Z]{2,}(?:\.\d+)+"
OBJECT_PREFIX = r"(?:tables?|figures?|figs?\.?)"


def strip_document_prefix(text: str, alias: str) -> str | None:
    """Strip one exact known identity; only an explicit edition permits a comma.

    Do not remove arbitrary punctuation before identifying the document. In
    particular a foreign edition must not fall back into the local namespace.
    Both arguments are already normalized with reference_key().
    """
    if text.startswith(alias + " "):
        return text[len(alias) + 1 :]
    if re.search(r":\d{4}$", alias) and text.startswith(alias + ","):
        return text[len(alias) + 1 :].strip() or None
    return None


def strip_document_qualifier(text: str, alias: str) -> str | None:
    coordinate = strip_document_prefix(text, alias)
    if coordinate is not None:
        return coordinate
    suffix = " of " + alias
    return text[: -len(suffix)] if text.endswith(suffix) else None
