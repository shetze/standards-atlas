"""File-system adapters."""

from standards_atlas.adapters.filesystem.document_repository import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.adapters.filesystem.formula_transcription_repository import (
    FileSystemFormulaTranscriptionRepository,
)
from standards_atlas.adapters.filesystem.knowledge_proposal_repository import (
    FileSystemDocumentKnowledgeProposalRepository,
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

from .publication_document_provider import FileSystemPublicationDocumentProvider

__all__ = [
    "FileSystemPublicationDocumentProvider",
    "FileSystemEngineeringDocumentRepository",
    "FileSystemFormulaTranscriptionRepository",
    "FileSystemKnowledgeTableRepository",
    "FileSystemDocumentKnowledgeProposalRepository",
    "FileSystemNormalizedTableRepository",
    "FileSystemTableRetrievalProjectionRepository",
    "FileSystemFormalSemanticProjectionRepository",
]

from .formal_semantic_projection_repository import FileSystemFormalSemanticProjectionRepository
