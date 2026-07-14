"""Orchestrate deterministic document alignment."""

from pathlib import Path

from standards_atlas.adapters.alignment import AlignmentArtifactRepository
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
from standards_atlas.application.alignment import AlignmentEngine
from standards_atlas.application.model.alignment import AlignmentOptions, AlignmentResult
from standards_atlas.domain.model import DocumentKey


class AlignmentService:
    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._documents = FileSystemEngineeringDocumentRepository(workspace)
        self._normalized = NormalizationArtifactRepository(workspace)
        self._candidates = ReferenceCandidateRepository(workspace)
        self._results = AlignmentArtifactRepository(workspace)
        self._engine = AlignmentEngine()

    def run(
        self,
        document_key: str,
        options: AlignmentOptions | None = None,
    ) -> AlignmentResult:
        engineering = self._documents.load(DocumentKey(value=document_key))
        normalized = self._normalized.load(document_key)
        candidates = self._candidates.load(document_key)
        result = self._engine.align(normalized, candidates, engineering, options)
        self._results.save(document_key, result)
        return result

    def load(self, document_key: str) -> AlignmentResult:
        return self._results.load(document_key)
