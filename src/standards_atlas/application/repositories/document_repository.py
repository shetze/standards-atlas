"""Repository port for persisted engineering documents."""

from __future__ import annotations

from typing import Protocol

from standards_atlas.domain.model import DocumentKey, EngineeringDocument


class EngineeringDocumentRepository(Protocol):
    """Repository for derived EngineeringDocument state."""

    def save(self, document: EngineeringDocument) -> None:
        """Persist an engineering document."""
        ...

    def load(self, key: DocumentKey) -> EngineeringDocument:
        """Load an engineering document by key."""
        ...

    def exists(self, key: DocumentKey) -> bool:
        """Return whether a document exists."""
        ...
