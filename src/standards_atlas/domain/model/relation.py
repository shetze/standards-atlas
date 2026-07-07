"""Traceability relation model for Standards Atlas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model.identifiers import ClauseId


class RelationType(StrEnum):
    """Semantic type of a traceability relation."""

    RELATES_TO = "relates_to"
    EQUIVALENT_TO = "equivalent_to"
    REFINES = "refines"
    SATISFIES = "satisfies"
    REFERENCES = "references"
    CONFLICTS_WITH = "conflicts_with"


class Relation(BaseModel):
    """A semantic relation between two clauses or requirements."""

    model_config = ConfigDict(frozen=True)

    source_id: ClauseId
    target_id: ClauseId
    relation_type: RelationType

    rationale: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str | None = None
