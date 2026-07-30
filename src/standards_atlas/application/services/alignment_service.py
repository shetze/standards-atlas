"""Orchestrate deterministic document alignment."""

from standards_atlas.application.alignment import AlignmentEngine
from standards_atlas.application.model.alignment import AlignmentOptions, AlignmentResult
from standards_atlas.application.ports import (
    AlignmentStore,
    EngineeringDocumentRepository,
    NormalizationRepository,
    ReferenceCandidateStore,
)
from standards_atlas.domain.model import DocumentKey


class AlignmentService:
    def __init__(
        self,
        documents: EngineeringDocumentRepository,
        normalized: NormalizationRepository,
        candidates: ReferenceCandidateStore,
        results: AlignmentStore,
        engine: AlignmentEngine | None = None,
    ) -> None:
        self._documents = documents
        self._normalized = normalized
        self._candidates = candidates
        self._results = results
        self._engine = engine or AlignmentEngine()

    def run(self, document_key: str, options: AlignmentOptions | None = None) -> AlignmentResult:
        engineering = self._documents.load(DocumentKey(value=document_key))
        normalized = self._normalized.load(document_key)
        candidates = self._candidates.load(document_key)
        result = self._engine.align(normalized, candidates, engineering, options)
        self._results.save(document_key, result)
        return result

    def load(self, document_key: str) -> AlignmentResult:
        return self._results.load(document_key)
