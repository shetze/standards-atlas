"""Human-readable semantic extraction clause references."""

from __future__ import annotations

from standards_atlas.domain.model import StandardReference


def display_clause_reference(document_key: str, reference: StandardReference) -> str:
    """Render the canonical human-readable clause reference."""
    del document_key  # part identity is carried by StandardReference itself
    return reference.as_text()
