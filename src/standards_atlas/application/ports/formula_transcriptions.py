"""Ports used by formula transcription enrichment."""

from typing import Protocol

from standards_atlas.application.model.formula_transcription import FormulaTranscriptionArtifact
from standards_atlas.domain.model import DocumentKey, EngineeringDocument


class FormulaTranscriptionDocumentRepository(Protocol):
    """Canonical document persistence required by formula enrichment."""

    def load(self, key: DocumentKey) -> EngineeringDocument: ...
    def list(self) -> tuple[EngineeringDocument, ...]: ...
    def save(self, document: EngineeringDocument) -> None: ...


class FormulaTranscriptionRepository(Protocol):
    """Persistence for formula transcription enrichment artifacts."""

    def save(self, artifact: FormulaTranscriptionArtifact) -> None: ...
    def load(self, formula_id: str) -> FormulaTranscriptionArtifact: ...
    def exists(self, formula_id: str) -> bool: ...
