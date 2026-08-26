"""File-system adapters."""

from standards_atlas.adapters.filesystem.document_repository import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.adapters.filesystem.formula_transcription_repository import (
    FileSystemFormulaTranscriptionRepository,
)
from standards_atlas.adapters.filesystem.knowledge_table_repository import (
    FileSystemKnowledgeTableRepository,
)
from standards_atlas.adapters.filesystem.normalized_table_repository import (
    FileSystemNormalizedTableRepository,
)
from standards_atlas.adapters.filesystem.retrieval_projection_repository import (
    FileSystemTableRetrievalProjectionRepository,
)

__all__ = [
    "FileSystemEngineeringDocumentRepository",
    "FileSystemFormulaTranscriptionRepository",
    "FileSystemKnowledgeTableRepository",
    "FileSystemNormalizedTableRepository",
    "FileSystemTableRetrievalProjectionRepository",
    "FileSystemFormalSemanticProjectionRepository",
    "FileSystemSemanticExtractionRepository",
]

from .formal_semantic_projection_repository import FileSystemFormalSemanticProjectionRepository
from .semantic_extraction_repository import FileSystemSemanticExtractionRepository
