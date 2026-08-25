"""Ports for ontology-guided semantic knowledge extraction."""

from __future__ import annotations

from typing import Protocol

from standards_atlas.domain.model import (
    Clause,
    ClauseSemanticExtraction,
    DocumentSemanticExtraction,
)


class SemanticKnowledgeExtractor(Protocol):
    """Extract ontology-grounded entities and relations from one eligible clause."""

    def extract(
        self,
        clause: Clause,
        *,
        document_key: str,
        ontology_versions: tuple[str, ...],
    ) -> ClauseSemanticExtraction: ...


class SemanticExtractionRepository(Protocol):
    """Persistence boundary for rebuildable semantic extraction artifacts."""

    def save(self, extraction: DocumentSemanticExtraction) -> None: ...

    def load(self, document_key: str) -> DocumentSemanticExtraction | None: ...
