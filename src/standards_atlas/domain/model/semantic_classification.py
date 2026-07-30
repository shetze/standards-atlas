"""Multidimensional semantic classification of clause-like items."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StatementFunction(StrEnum):
    """Linguistic or logical function performed by a statement."""

    REQUIREMENT = "requirement"
    RECOMMENDATION = "recommendation"
    PERMISSION = "permission"
    PROHIBITION = "prohibition"
    DEFINITION = "definition"
    DESCRIPTION = "description"
    EXPLANATION = "explanation"
    RATIONALE = "rationale"
    EXAMPLE = "example"
    NOTE = "note"
    GUIDELINE = "guideline"
    CONFORMANCE_STATEMENT = "conformance_statement"


class ApplicabilityFunction(StrEnum):
    """How a statement constrains the scope or applicability of normative content."""

    SCOPE_DEFINITION = "scope_definition"
    APPLICABILITY_CONDITION = "applicability_condition"
    INCLUSION = "inclusion"
    EXCLUSION = "exclusion"
    EXCEPTION = "exception"


class ResponsibilityFunction(StrEnum):
    """How a statement allocates responsibility to roles or actors."""

    RESPONSIBILITY_ASSIGNMENT = "responsibility_assignment"
    RESPONSIBILITY_EXCLUSION = "responsibility_exclusion"
    ROLE_CONDITION = "role_condition"


class DocumentStructure(StrEnum):
    """Small document-family-neutral structural vocabulary."""

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
    """Normative force of a clause or document part."""

    NORMATIVE = "normative"
    INFORMATIVE = "informative"
    MIXED = "mixed"
    UNSPECIFIED = "unspecified"
    NOT_APPLICABLE = "not_applicable"


class RelationScope(StrEnum):
    """Whether a relation target belongs to the same document."""

    INTERNAL = "internal"
    EXTERNAL = "external"


class SemanticRelationKind(StrEnum):
    """Meaning of a semantic relation."""

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
    """Structural classification qualified by a document-family taxonomy."""

    model_config = ConfigDict(frozen=True)

    family: str = Field(min_length=1)
    category: DocumentStructure
    function: str | None = None
    annex_identifier: str | None = None


class DomainFunctionClassification(BaseModel):
    """Functions assigned using one versioned KnowledgeDomain taxonomy."""

    model_config = ConfigDict(frozen=True)

    knowledge_domain: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    functions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def functions_are_unique(self) -> DomainFunctionClassification:
        if len(self.functions) != len(set(self.functions)):
            raise ValueError("domain functions must not contain duplicates")
        return self


class SemanticRelation(BaseModel):
    """Resolved semantic relation from the containing clause to a target."""

    model_config = ConfigDict(frozen=True)

    kind: SemanticRelationKind
    scope: RelationScope
    target_reference: str = Field(min_length=1)
    target_clause_id: str | None = None
    target_document_key: str | None = None
    display_text: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = None

    @model_validator(mode="after")
    def external_target_has_document(self) -> SemanticRelation:
        if self.scope is RelationScope.EXTERNAL and not self.target_document_key:
            raise ValueError("external relations require target_document_key")
        return self


class SemanticClassification(BaseModel):
    """Independent semantic dimensions assigned to one clause-like item."""

    model_config = ConfigDict(frozen=True)

    statement_functions: tuple[StatementFunction, ...] = ()
    applicability_functions: tuple[ApplicabilityFunction, ...] = ()
    responsibility_functions: tuple[ResponsibilityFunction, ...] = ()
    document_structure: DocumentStructureClassification | None = None
    normative_status: NormativeStatus = NormativeStatus.UNSPECIFIED
    domain_functions: tuple[DomainFunctionClassification, ...] = ()
    relations: tuple[SemanticRelation, ...] = ()

    @model_validator(mode="after")
    def dimensions_are_unique(self) -> SemanticClassification:
        if len(self.statement_functions) != len(set(self.statement_functions)):
            raise ValueError("statement_functions must not contain duplicates")
        if len(self.applicability_functions) != len(set(self.applicability_functions)):
            raise ValueError("applicability_functions must not contain duplicates")
        if len(self.responsibility_functions) != len(set(self.responsibility_functions)):
            raise ValueError("responsibility_functions must not contain duplicates")
        domains = [item.knowledge_domain for item in self.domain_functions]
        if len(domains) != len(set(domains)):
            raise ValueError("each knowledge domain may occur only once")
        return self
