"""Orchestrate clause-reference candidate detection."""

import re

from standards_atlas.application.analysis import ReferenceCandidateDetector
from standards_atlas.application.model.reference_candidates import ReferenceCandidateDocument
from standards_atlas.application.ports import (
    EngineeringDocumentRepository,
    NormalizationRepository,
    ReferenceCandidateStore,
)
from standards_atlas.application.services.document_selection_service import (
    DocumentSelectionService,
)
from standards_atlas.domain.model import DocumentKey


class ReferenceCandidateService:
    def __init__(
        self,
        documents: EngineeringDocumentRepository,
        normalized: NormalizationRepository,
        results: ReferenceCandidateStore,
        selection: DocumentSelectionService,
        detector: ReferenceCandidateDetector | None = None,
    ) -> None:
        self._documents = documents
        self._normalized = normalized
        self._results = results
        self._selection = selection
        self._detector = detector or ReferenceCandidateDetector()

    def detect(self, document_key: str) -> ReferenceCandidateDocument:
        engineering = self._load_or_derive_document(document_key)
        normalized = self._normalized.load(document_key)
        result = self._detector.detect(normalized, engineering)
        self._results.save(document_key, result)
        return result

    def load(self, document_key: str) -> ReferenceCandidateDocument:
        return self._results.load(document_key)

    def _load_or_derive_document(self, document_key: str):
        key = DocumentKey(value=document_key)
        if self._documents.exists(key):
            return self._documents.load(key)

        match = re.fullmatch(r"(?P<parent>.+)-(?P<volume>[^-]+)", document_key)
        if match is None:
            return self._documents.load(key)

        parent_key = match.group("parent")
        parent = DocumentKey(value=parent_key)
        if not self._documents.exists(parent):
            return self._documents.load(key)

        return self._selection.derive_by_volume(
            parent_key,
            document_key,
            match.group("volume"),
            document_key,
        )
