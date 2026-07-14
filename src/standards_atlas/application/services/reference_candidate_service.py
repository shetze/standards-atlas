"""Orchestrate clause-reference candidate detection."""

from pathlib import Path

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
from standards_atlas.application.analysis import ReferenceCandidateDetector
from standards_atlas.application.model.reference_candidates import ReferenceCandidateDocument
from standards_atlas.domain.model import DocumentKey


class ReferenceCandidateService:
    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._documents = FileSystemEngineeringDocumentRepository(workspace)
        self._normalized = NormalizationArtifactRepository(workspace)
        self._results = ReferenceCandidateRepository(workspace)
        self._detector = ReferenceCandidateDetector()

    def detect(self, document_key: str) -> ReferenceCandidateDocument:
        engineering = self._documents.load(DocumentKey(value=document_key))
        normalized = self._normalized.load(document_key)
        result = self._detector.detect(normalized, engineering)
        self._results.save(document_key, result)
        return result

    def load(self, document_key: str) -> ReferenceCandidateDocument:
        return self._results.load(document_key)
