"""Reference mentions preserved for later taxonomy and ontology processing."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReferenceMentionKind(StrEnum):
    CLAUSE = "clause"
    CLAUSE_RANGE = "clause_range"
    CONTEXTUAL_CLAUSE = "contextual_clause"
    DOCUMENT = "document"


class ReferenceResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    DEFERRED = "deferred"


class ReferenceTarget(BaseModel):
    model_config = ConfigDict(frozen=True)
    document_key: str | None = None
    clause_id: str | None = None
    reference: str = Field(min_length=1)
    title: str | None = None


class ReferenceMention(BaseModel):
    """Lossless syntactic reference evidence; unresolved mentions are valid output."""

    model_config = ConfigDict(frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    kind: ReferenceMentionKind
    surface_text: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    reference: str | None = None
    range_start: str | None = None
    range_end: str | None = None
    direction_hint: Literal["self", "forward", "backward"] | None = None
    cardinality_hint: Literal["one", "multiple"] | None = None
    status: ReferenceResolutionStatus
    targets: tuple[ReferenceTarget, ...] = ()
