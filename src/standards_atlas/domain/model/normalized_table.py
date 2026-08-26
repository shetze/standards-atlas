"""Canonical structural normalization of protected table content."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model.source_evidence import SourceEvidence
from standards_atlas.domain.model.table_structure import DocumentTableId


class NormalizedTableRowKind(StrEnum):
    """Structural role of one normalized table row."""

    HEADER = "header"
    DATA = "data"
    FOOTNOTE = "footnote"


class NormalizedTableCell(BaseModel):
    """One anchor cell placed at deterministic logical coordinates."""

    model_config = ConfigDict(frozen=True)

    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    text: str
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    is_header: bool = False


class NormalizedTableColumn(BaseModel):
    """One logical column with a flattened multi-row header path."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    header_path: tuple[str, ...] = ()
    label: str | None = None
    unit: str | None = None


class NormalizedTableRow(BaseModel):
    """One logical row after span-aware grid placement."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    kind: NormalizedTableRowKind
    cells: tuple[NormalizedTableCell, ...] = ()
    header_path: tuple[str, ...] = ()


class NormalizedTableFootnote(BaseModel):
    """A structurally recognized table footnote retained verbatim."""

    model_config = ConfigDict(frozen=True)

    marker: str | None = None
    text: str
    row_index: int = Field(ge=0)


class NormalizedTableReference(BaseModel):
    """An unresolved structural reference token found inside a table cell."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)


class NormalizedTable(BaseModel):
    """Lossless deterministic normalization of one canonical ``TableBlock``.

    The model preserves cell text and spans while adding logical coordinates,
    header paths, structural footnotes, units, and unresolved reference tokens.
    It contains no domain or ontology interpretation.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    document_table_id: DocumentTableId | None = None
    document_key: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    title: str | None = None
    parent_clause_id: str = Field(min_length=1)
    parent_clause_reference: str = Field(min_length=1)
    table_block_id: str = Field(min_length=1)
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    header_row_count: int = Field(ge=0)
    columns: tuple[NormalizedTableColumn, ...] = ()
    rows: tuple[NormalizedTableRow, ...] = ()
    footnotes: tuple[NormalizedTableFootnote, ...] = ()
    references: tuple[NormalizedTableReference, ...] = ()
    source_evidence: tuple[SourceEvidence, ...] = ()
    normalization_version: str = "1.0.0"
