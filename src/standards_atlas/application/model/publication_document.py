"""Runtime-only read model used by publication adapters."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model import (
    ArtifactLineage,
    ArtifactReference,
    Clause,
    ClauseAnnotation,
    DocumentKey,
    DocumentTable,
    DocumentType,
    EngineeringDocument,
    TableIndexEntry,
)


class PublicationDocument(BaseModel):
    """Rebuildable publication projection of one document or document family.

    Publication documents are runtime read models. They are never canonical and
    are intentionally not persisted or schema-versioned.
    """

    model_config = ConfigDict(frozen=True)

    key: DocumentKey
    title: str = Field(min_length=1)
    document_type: DocumentType = DocumentType.OTHER
    year: int | None = None
    version: str | None = None
    source: str | None = None
    clauses: tuple[Clause, ...] = ()
    tables: tuple[DocumentTable, ...] = ()
    table_index: tuple[TableIndexEntry, ...] = ()
    annotations: tuple[ClauseAnnotation, ...] = ()
    lineage: ArtifactLineage | None = None
    source_artifacts: tuple[ArtifactReference, ...] = ()
    part_keys: tuple[str, ...] = ()

    @classmethod
    def from_engineering_document(cls, document: EngineeringDocument) -> PublicationDocument:
        """Project one canonical physical document into the publication read model."""
        return cls(
            key=DocumentKey(value=document.key.value),
            title=document.title,
            document_type=document.document_type,
            year=document.year,
            version=document.version,
            source=document.source,
            clauses=document.clauses,
            tables=document.tables,
            table_index=document.table_index,
            annotations=document.annotations,
            lineage=document.lineage,
            source_artifacts=((document.lineage.artifact,) if document.lineage is not None else ()),
            part_keys=(document.key.value,),
        )
