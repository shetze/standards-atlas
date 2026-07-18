"""Port for optional semantic-role classification extensions."""

from __future__ import annotations

from typing import Protocol

from standards_atlas.application.services.semantic_role_classifier import (
    SemanticRoleClassification,
    SemanticRoleContext,
)


class SemanticRoleClassifierExtension(Protocol):
    """Optional secondary classifier, for example an LLM-backed adapter.

    Extensions are invoked only when the deterministic classifier cannot produce
    a sufficiently confident result. Implementations must return evidence and
    confidence; they never mutate the document directly.
    """

    def classify(
        self,
        context: SemanticRoleContext,
    ) -> SemanticRoleClassification | None:
        """Classify one clause or return ``None`` when no result is available."""
