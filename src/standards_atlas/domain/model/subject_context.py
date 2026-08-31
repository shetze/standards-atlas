"""Canonical clause subject context for CBox enrichment."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SubjectEvidenceKind(StrEnum):
    """Deterministic evidence source supporting a primary subject decision."""

    CLAUSE_HEADING = "clause_heading"
    CLAUSE_TEXT = "clause_text"
    ANCESTOR_HEADING = "ancestor_heading"
    SCOPE_CONTEXT = "scope_context"


class SubjectContextEvidence(BaseModel):
    """Deterministic evidence supporting a primary subject assignment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: SubjectEvidenceKind
    matched_label: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    source_clause_id: str = Field(min_length=1)
    ancestor_distance: int | None = Field(default=None, ge=1)


class PrimarySubjectContext(BaseModel):
    """One deterministic primary subject projected into clause context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    normalized_label: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: SubjectContextEvidence


class ClauseSubjectContext(BaseModel):
    """Subject-oriented CBox enrichment for one clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    primary_subject: PrimarySubjectContext | None = None
    ambiguous_candidates: tuple[str, ...] = ()
