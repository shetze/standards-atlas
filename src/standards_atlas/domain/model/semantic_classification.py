"""Multidimensional semantic classification of clause-like items."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StatementFunction(StrEnum):
    """Linguistic or logical function performed by a statement."""

    REQUIREMENT = "requirement"
    RECOMMENDATION = "recommendation"
    CONDEMNATION = "condemnation"
    WARNING = "warning"
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
    OBJECTIVE = "objective"
    PREREQUISITE = "prerequisite"
    ASSUMPTION = "assumption"


class KnowledgeKind(StrEnum):
    """Kind of engineering knowledge represented by a clause."""

    TECHNIQUE = "technique"
    METHOD_OR_MEASURE = "method_or_measure"
    TECHNIQUE_OR_MEASURE = "technique_or_measure"
    PROCESS = "process"
    ARTIFACT = "artifact"
    ROLE = "role"
    EVIDENCE = "evidence"
    CONCEPT = "concept"


class ProcessFunction(StrEnum):
    """Role of a clause in a process or lifecycle model."""

    OBJECTIVE = "objective"
    PREREQUISITE = "prerequisite"
    INPUT = "input"
    ACTIVITY = "activity"
    DECISION = "decision"
    BRANCH = "branch"
    SEQUENCE = "sequence"
    OUTPUT = "output"
    COMPLETION_CRITERION = "completion_criterion"
    OPTION = "option"
    ASSUMPTION = "assumption"


class ApplicabilityFunction(StrEnum):
    """How a statement constrains the scope or applicability of normative content."""

    SCOPE_DEFINITION = "scope_definition"
    APPLICABILITY_CONDITION = "applicability_condition"
    INCLUSION = "inclusion"
    EXCLUSION = "exclusion"
    EXCEPTION = "exception"


class RoleRelationType(StrEnum):
    """Controlled relation types between an actor/role and a target."""

    RESPONSIBLE_FOR = "responsible_for"
    PERFORMS = "performs"
    APPROVES = "approves"
    VERIFIES = "verifies"
    VALIDATES = "validates"
    CONSULTED_FOR = "consulted_for"
    INFORMED_ABOUT = "informed_about"
    INDEPENDENT_OF = "independent_of"
    EXCLUDED_FROM = "excluded_from"
    ASSIGNED_TO = "assigned_to"
    ASSUMES_ROLE = "assumes_role"
    PARTICIPATES_IN = "participates_in"


class RoleRelation(BaseModel):
    """Evidence-grounded relation between a role/actor and an activity, artifact, or role."""

    model_config = ConfigDict(frozen=True)

    role: str = Field(min_length=1)
    relation: RoleRelationType
    target: str = Field(min_length=1)
    condition: str | None = None
    evidence: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


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
    knowledge_kinds: tuple[KnowledgeKind, ...] = ()
    process_functions: tuple[ProcessFunction, ...] = ()
    applicability_functions: tuple[ApplicabilityFunction, ...] = ()
    role_relation_types: tuple[RoleRelationType, ...] = ()
    role_relations: tuple[RoleRelation, ...] = ()
    document_structure: DocumentStructureClassification | None = None
    normative_status: NormativeStatus = NormativeStatus.UNSPECIFIED
    domain_functions: tuple[DomainFunctionClassification, ...] = ()
    relations: tuple[SemanticRelation, ...] = ()

    @model_validator(mode="after")
    def dimensions_are_unique(self) -> SemanticClassification:
        if len(self.statement_functions) != len(set(self.statement_functions)):
            raise ValueError("statement_functions must not contain duplicates")
        if len(self.knowledge_kinds) != len(set(self.knowledge_kinds)):
            raise ValueError("knowledge_kinds must not contain duplicates")
        if len(self.process_functions) != len(set(self.process_functions)):
            raise ValueError("process_functions must not contain duplicates")
        if len(self.applicability_functions) != len(set(self.applicability_functions)):
            raise ValueError("applicability_functions must not contain duplicates")
        if len(self.role_relation_types) != len(set(self.role_relation_types)):
            raise ValueError("role_relation_types must not contain duplicates")
        relation_keys = [
            (item.role, item.relation, item.target, item.condition) for item in self.role_relations
        ]
        if len(relation_keys) != len(set(relation_keys)):
            raise ValueError("role_relations must not contain duplicates")
        domains = [item.knowledge_domain for item in self.domain_functions]
        if len(domains) != len(set(domains)):
            raise ValueError("each knowledge domain may occur only once")
        return self
