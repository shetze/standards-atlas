"""Shared deterministic text normalization operations."""

from __future__ import annotations

import re
import unicodedata

from standards_atlas.application.model.normalized_document import NormalizationOptions


def normalize_text(value: str, options: NormalizationOptions) -> str:
    """Normalize prose while preserving its semantic content."""
    value = unicodedata.normalize(options.unicode_form, value)
    value = _remove_control_characters(value)
    value = value.replace("\u00a0", " ").replace("\u2007", " ").replace("\u202f", " ")
    if options.normalize_whitespace:
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\s*\n\s*", " ", value)
    return value.strip()


def normalize_code(value: str, options: NormalizationOptions) -> str:
    """Normalize code while retaining line breaks and indentation."""
    value = unicodedata.normalize(options.unicode_form, value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return _remove_control_characters(value).strip("\n")


def normalize_optional_text(
    value: str | None,
    options: NormalizationOptions,
) -> str | None:
    """Normalize an optional prose value."""
    return normalize_text(value, options) if value is not None else None


def _remove_control_characters(value: str) -> str:
    return "".join(
        character
        for character in value
        if character in "\n\t" or unicodedata.category(character) != "Cc"
    )
