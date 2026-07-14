"""Clause-reference candidates detected in normalized documents."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReferenceMatchKind(StrEnum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    INLINE = "inline"
    ANNEX = "annex"


class CandidateRemainderKind(StrEnum):
    TITLE = "title"
    CONTENT = "content"
    UNKNOWN = "unknown"


class ReferenceCandidateStatus(StrEnum):
    EXPECTED = "expected"
    UNEXPECTED = "unexpected"
    AMBIGUOUS = "ambiguous"


class ReferenceCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_id: str
    sequence_number: int = Field(ge=0)
    raw_reference: str
    normalized_reference: str
    title_remainder: str | None = None
    remainder_kind: CandidateRemainderKind = CandidateRemainderKind.UNKNOWN
    following_label_item_id: str | None = None
    following_label: str | None = None
    match_kind: ReferenceMatchKind
    status: ReferenceCandidateStatus
    confidence: float = Field(ge=0.0, le=1.0)
    expected_clause_ids: tuple[str, ...] = ()


class ReferenceDetectionIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: str = "warning"
    item_ids: tuple[str, ...] = ()
    message: str


class ReferenceDetectionStatistics(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_items: int = 0
    candidates: int = 0
    expected_candidates: int = 0
    unexpected_candidates: int = 0
    ambiguous_candidates: int = 0
    exact_matches: int = 0
    normalized_matches: int = 0
    inline_matches: int = 0
    annex_matches: int = 0


class ReferenceDetectionMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 2
    detector_version: str
    source_normalization_hash: str
    expected_structure_hash: str
    created_at: datetime
    statistics: ReferenceDetectionStatistics


class ReferenceCandidateDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    candidates: tuple[ReferenceCandidate, ...] = ()
    issues: tuple[ReferenceDetectionIssue, ...] = ()
    metadata: ReferenceDetectionMetadata
