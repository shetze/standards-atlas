"""Deterministic alignment of reference candidates with AtlasData structure."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.model.reference_candidates import (
    CandidateRemainderKind,
    ReferenceMatchKind,
)


class AlignmentStatus(StrEnum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    ANNEX = "annex"
    SEQUENCE_INFERRED = "sequence_inferred"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"
    CONFLICTING = "conflicting"
    MANUAL = "manual"


class AlignmentIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    clause_ids: tuple[str, ...] = ()
    item_ids: tuple[str, ...] = ()
    message: str


class ClauseAlignment(BaseModel):
    model_config = ConfigDict(frozen=True)

    clause_id: str
    expected_reference: str
    candidate_item_id: str | None = None
    status: AlignmentStatus
    match_kind: ReferenceMatchKind | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    start_sequence_number: int | None = Field(default=None, ge=0)
    end_sequence_number: int | None = Field(default=None, ge=0)
    source_item_ids: tuple[str, ...] = ()
    observed_title: str | None = None
    observed_remainder: str | None = None
    remainder_kind: CandidateRemainderKind | None = None
    following_label_item_id: str | None = None
    following_label: str | None = None
    alternative_item_ids: tuple[str, ...] = ()
    manual_heading_level: int | None = Field(default=None, ge=1)


class UnassignedRange(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["front_matter", "between_clauses", "back_matter"]
    start_sequence_number: int = Field(ge=0)
    end_sequence_number: int = Field(ge=0)
    source_item_ids: tuple[str, ...] = ()


class AlignmentStatistics(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_clauses: int = 0
    exact_matches: int = 0
    normalized_matches: int = 0
    annex_matches: int = 0
    inferred_matches: int = 0
    ambiguous: int = 0
    missing: int = 0
    conflicting: int = 0
    unassigned_ranges: int = 0


class AlignmentOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    infer_single_missing_clause: bool = True
    title_similarity_threshold: float = Field(default=0.55, ge=0.0, le=1.0)


class AlignmentMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 2
    alignment_version: str
    normalized_document_hash: str
    candidate_document_hash: str
    expected_structure_hash: str
    created_at: datetime
    options: AlignmentOptions
    statistics: AlignmentStatistics


class AlignmentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    clauses: tuple[ClauseAlignment, ...] = ()
    unassigned_ranges: tuple[UnassignedRange, ...] = ()
    issues: tuple[AlignmentIssue, ...] = ()
    metadata: AlignmentMetadata
