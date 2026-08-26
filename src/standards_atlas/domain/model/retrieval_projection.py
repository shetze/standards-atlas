"""Disposable retrieval projections derived from canonical knowledge artifacts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RetrievalDocumentKind(StrEnum):
    """Granularity of one retrieval-oriented projection."""

    TABLE = "table"
    ROW = "row"
    CONCEPT = "concept"
    RELATION = "relation"


class RetrievalTokenizationProfile(StrEnum):
    """Tokenizer contract requested by a retrieval projection."""

    STRUCTURED_TABLE_V1 = "structured-table-v1"


class RetrievalDocument(BaseModel):
    """One deterministic, disposable input document for a retrieval index."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    kind: RetrievalDocumentKind
    document_key: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    tokenization_profile: RetrievalTokenizationProfile
    metadata: dict[str, str] = Field(default_factory=dict)


class RetrievalProjection(BaseModel):
    """Versioned set of retrieval documents derived from structured table knowledge."""

    model_config = ConfigDict(frozen=True)

    source_table_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    documents: tuple[RetrievalDocument, ...] = ()
    projection_version: str = "1.0.0"
