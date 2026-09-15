"""Clause-level structural and reference semantics retained by the canonical model."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentStructure(StrEnum):
    FRONT_MATTER = "front_matter"
    FOREWORD = "foreword"
    INTRODUCTION = "introduction"
    SCOPE = "scope"
    REFERENCES = "references"
    TERMINOLOGY = "terminology"
    BODY = "body"
    ANNEX = "annex"
    BIBLIOGRAPHY = "bibliography"
    BACK_MATTER = "back_matter"


class NormativeStatus(StrEnum):
    NORMATIVE = "normative"
    INFORMATIVE = "informative"
    MIXED = "mixed"
    UNSPECIFIED = "unspecified"
    NOT_APPLICABLE = "not_applicable"


class RelationScope(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class SemanticRelationKind(StrEnum):
    REFERENCES = "references"
    NORMATIVE_REFERENCE = "normative_reference"
    INFORMATIVE_REFERENCE = "informative_reference"
    REFINES = "refines"
    IMPLEMENTS = "implements"
    VERIFIES = "verifies"
    VALIDATES = "validates"
    DEPENDS_ON = "depends_on"
    CONFLICTS_WITH = "conflicts_with"
    EQUIVALENT_TO = "equivalent_to"
    DERIVED_FROM = "derived_from"
    APPLIES_TO = "applies_to"
    PROVIDES_EVIDENCE_FOR = "provides_evidence_for"


class DocumentStructureClassification(BaseModel):
    model_config = ConfigDict(frozen=True)
    family: str = Field(min_length=1)
    category: DocumentStructure
    function: str | None = None
    annex_identifier: str | None = None


class SemanticRelation(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: SemanticRelationKind
    scope: RelationScope
    target_reference: str = Field(min_length=1)
    target_clause_id: str | None = None
    target_document_key: str | None = None
    display_text: str | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def external_target_has_document(self) -> SemanticRelation:
        if self.scope is RelationScope.EXTERNAL and not self.target_document_key:
            raise ValueError("external relations require target_document_key")
        return self
