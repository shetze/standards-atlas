"""Create deterministic derived views of persisted engineering documents."""

from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.domain.model import (
    ClauseId,
    DocumentKey,
    DocumentTable,
    EngineeringDocument,
    Standard,
    StandardKey,
    TableIndexEntry,
)


class DocumentSelectionError(ValueError):
    """Raised when a requested document selection cannot be created."""


class DocumentSelectionService:
    """Derive a physical-source-sized document from a logical master document."""

    def __init__(
        self,
        documents: EngineeringDocumentRepository,
        target_documents: EngineeringDocumentRepository | None = None,
    ) -> None:
        self._documents = documents
        self._target_documents = target_documents or documents

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
        derived = select_document_part(source, target_key, volume, title)
        self._target_documents.save(derived)
        return derived

    def _persist_selection(
        self,
        source: EngineeringDocument,
        target_key: str,
        clauses: tuple,
        title: str,
    ) -> EngineeringDocument:
        clause_ids = {clause.id for clause in clauses}
        tables, table_index = _select_table_structure(source, clause_ids)
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
                    "tables": tables,
                    "table_index": table_index,
                }
            )
        else:
            derived = source.model_copy(
                update={
                    "key": DocumentKey(value=target_key),
                    "title": title,
                    "clauses": clauses,
                    "annotations": annotations,
                    "tables": tables,
                    "table_index": table_index,
                }
            )
        self._target_documents.save(derived)
        return derived


def select_document_part(
    source: EngineeringDocument,
    target_key: str,
    part: str,
    title: str | None = None,
) -> EngineeringDocument:
    """Pure physical part projection shared by canonical import and AtlasData restore."""
    clauses = tuple(clause for clause in source.clauses if clause.reference.part == part)
    if not clauses:
        raise DocumentSelectionError(
            f"Document {source.key.value!r} contains no clauses for volume {part!r}."
        )
    root_title = f"Part {part.replace('§', '-')}"
    clauses = tuple(
        clause.with_baseline_updates(heading=root_title)
        if clause.reference.clause.strip() == "0"
        else clause
        for clause in clauses
    )
    clause_ids = {clause.id for clause in clauses}
    tables, table_index = _select_table_structure(source, clause_ids)
    updates = {
        "key": DocumentKey(value=target_key),
        "title": title or root_title,
        "clauses": clauses,
        "annotations": tuple(a for a in source.annotations if a.clause_id in clause_ids),
        "tables": tables,
        "table_index": table_index,
    }
    if isinstance(source, Standard):
        updates.update(
            key=StandardKey(value=target_key),
            name=title or root_title,
            parent_key=StandardKey(value=source.key.value),
        )
    return source.model_copy(update=updates)


def _select_table_structure(
    source: EngineeringDocument,
    clause_ids: set[ClauseId],
) -> tuple[tuple[DocumentTable, ...], tuple[TableIndexEntry, ...]]:
    """Select related tables by parent identity, never by a part-local label.

    Unassigned tables and unlinked index entries remain in the master; without
    a parent identity there is no safe basis for assigning them to a part.
    """
    tables = tuple(table for table in source.tables if table.parent_clause_id in clause_ids)
    table_ids = {table.id for table in tables}
    table_index = tuple(entry for entry in source.table_index if entry.table_id in table_ids)
    return tables, table_index
