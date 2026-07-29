"""Traceability relation model for Standards Atlas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.domain.model.identifiers import ClauseId, DocumentKey


class RelationType(StrEnum):
    """Semantic type of a traceability relation."""

    RELATES_TO = "relates_to"
    EQUIVALENT_TO = "equivalent_to"
    REFINES = "refines"
    SATISFIES = "satisfies"
    REFERENCES = "references"
    CONFLICTS_WITH = "conflicts_with"


class RelationScope(StrEnum):
    """Whether a relation stays inside one document or crosses its boundary."""

    INTERNAL = "internal"
    EXTERNAL = "external"
    UNSPECIFIED = "unspecified"


class Relation(BaseModel):
    """A semantic relation between clauses or requirements.

    Existing same-document relations remain valid without additional fields.
    Cross-document relations identify the target document explicitly and use
    ``scope='external'``. This distinction is orthogonal to ``relation_type``:
    an internal and an external relation may both be references, refinements,
    conflicts, or another semantic relation type.
    """

    model_config = ConfigDict(frozen=True)

    source_id: ClauseId
    target_id: ClauseId
    relation_type: RelationType
    scope: RelationScope = RelationScope.UNSPECIFIED
    target_document_key: DocumentKey | None = None

    rationale: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> Relation:
        if self.scope == RelationScope.EXTERNAL and self.target_document_key is None:
            raise ValueError("external relations require target_document_key")
        if self.scope == RelationScope.INTERNAL and self.target_document_key is not None:
            raise ValueError("internal relations must not define target_document_key")
        return self
