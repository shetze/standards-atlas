"""Runtime publication projection backed by canonical engineering documents."""

from __future__ import annotations

from standards_atlas.adapters.filesystem.document_repository import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.application.model import PublicationDocument
from standards_atlas.application.services.document_composition_service import (
    DocumentCompositionService,
)


class FileSystemPublicationDocumentProvider:
    """Build publication read models on demand from canonical physical documents."""

    def __init__(self, documents: FileSystemEngineeringDocumentRepository) -> None:
        self._composition = DocumentCompositionService(documents)

    def load(
        self,
        document_key: str,
        *,
        part_keys: tuple[str, ...] = (),
        family_title: str | None = None,
    ) -> PublicationDocument:
        if part_keys:
            return self._composition.compose(
                document_key,
                part_keys,
                family_title=family_title,
            )
        return self._composition.project(document_key)

    def list(self) -> tuple[PublicationDocument, ...]:
        return self._composition.list_physical()
