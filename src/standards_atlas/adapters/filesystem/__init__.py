"""File-system adapters."""

from standards_atlas.adapters.filesystem.document_repository import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.adapters.filesystem.knowledge_table_repository import (
    FileSystemKnowledgeTableRepository,
)

__all__ = [
    "FileSystemEngineeringDocumentRepository",
    "FileSystemKnowledgeTableRepository",
]
