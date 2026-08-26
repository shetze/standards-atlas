"""First-class structural table metadata for engineering documents."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model.identifiers import ClauseId
from standards_atlas.domain.model.source_evidence import SourceEvidence


class DocumentTableId(BaseModel):
    """Stable identity of a table inside an engineering document."""

    model_config = ConfigDict(frozen=True)
    value: str = Field(min_length=1)


class TableIndexEntry(BaseModel):
    """One public entry declared by a document's List of Tables."""

    model_config = ConfigDict(frozen=True)
    reference: str = Field(min_length=1)
    title: str | None = None
    table_id: DocumentTableId | None = None


class DocumentTable(BaseModel):
    """First-class structural identity and location of one document table.

    Cell content remains canonical in the referenced ``TableBlock``.  T1 records
    only structural metadata so AtlasData can expose table identity without
    publishing protected table content.
    """

    model_config = ConfigDict(frozen=True)

    id: DocumentTableId
    reference: str = Field(min_length=1)
    title: str | None = None
    parent_clause_id: ClauseId | None = None
    parent_clause_reference: str | None = None
    sequence_index: int = Field(ge=0)
    table_block_id: str | None = None
    listed_in_table_index: bool = False
    source_evidence: tuple[SourceEvidence, ...] = ()
