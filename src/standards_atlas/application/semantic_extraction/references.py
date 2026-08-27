"""Human-readable semantic extraction clause references."""

from __future__ import annotations

import re

from standards_atlas.domain.model import StandardReference


def display_clause_reference(document_key: str, reference: StandardReference) -> str:
    """Render a clause reference including a part suffix carried by the document key."""
    standard = reference.standard
    normalized_standard = _normalized_key(standard)
    normalized_document = _normalized_key(document_key)
    if normalized_document.startswith(normalized_standard):
        suffix = normalized_document[len(normalized_standard) :]
        if suffix and suffix not in _normalized_key(standard):
            standard = f"{standard}{suffix}"
    if reference.year is None:
        return f"{standard} {reference.clause}"
    return f"{standard}:{reference.year} {reference.clause}"


def _normalized_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "", value)
