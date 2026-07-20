"""Create deterministic derived views of persisted engineering documents."""

from pathlib import Path

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.domain.model import DocumentKey, EngineeringDocument, Standard, StandardKey


class DocumentSelectionError(ValueError):
    """Raised when a requested document selection cannot be created."""


class DocumentSelectionService:
    """Derive a physical-source-sized document from a logical master document."""

    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._documents = FileSystemEngineeringDocumentRepository(workspace)

    def derive_by_standard_name(
        self,
        source_key: str,
        target_key: str,
        standard_name: str,
    ) -> EngineeringDocument:
        source = self._documents.load(DocumentKey(value=source_key))
        clauses = tuple(
            clause for clause in source.clauses if clause.reference.standard == standard_name
        )
        if not clauses:
            raise DocumentSelectionError(
                f"Document {source_key!r} contains no clauses for standard {standard_name!r}."
            )

        return self._persist_selection(source, target_key, clauses, standard_name)

    def derive_by_volume(
        self,
        source_key: str,
        target_key: str,
        volume: str,
        title: str | None = None,
    ) -> EngineeringDocument:
        source = self._documents.load(DocumentKey(value=source_key))
        clauses = tuple(
            clause
            for clause in source.clauses
            if clause.volume == volume and clause.reference.clause.strip() != "0"
        )
        if not clauses:
            raise DocumentSelectionError(
                f"Document {source_key!r} contains no clauses for volume {volume!r}."
            )
        return self._persist_selection(
            source, target_key, clauses, title or f"{source.title}-{volume}"
        )

    def _persist_selection(
        self,
        source: EngineeringDocument,
        target_key: str,
        clauses: tuple,
        title: str,
    ) -> EngineeringDocument:
        clause_ids = {clause.id for clause in clauses}
        annotations = tuple(
            annotation for annotation in source.annotations if annotation.clause_id in clause_ids
        )
        if isinstance(source, Standard):
            derived: EngineeringDocument = source.model_copy(
                update={
                    "key": StandardKey(value=target_key),
                    "title": title,
                    "name": title,
                    "parent_key": StandardKey(value=source.key.value),
                    "clauses": clauses,
                    "annotations": annotations,
                }
            )
        else:
            derived = source.model_copy(
                update={
                    "key": DocumentKey(value=target_key),
                    "title": title,
                    "clauses": clauses,
                    "annotations": annotations,
                }
            )
        self._documents.save(derived)
        return derived
