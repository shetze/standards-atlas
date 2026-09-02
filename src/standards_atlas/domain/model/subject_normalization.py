"""Canonical lexical normalization for primary-subject identities."""

from __future__ import annotations

import re
import unicodedata

_DASHES = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
    }
)
_WHITESPACE = re.compile(r"\s+")


def normalize_subject_label(label: str) -> str:
    """Normalize lexical variants without introducing semantic equivalence."""

    normalized = unicodedata.normalize("NFKC", label).translate(_DASHES).casefold()
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    return normalized.strip(" \t\r\n.,;:")
