"""Non-canonical proposal contracts for assertion-centred engineering knowledge."""

from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from standards_atlas.domain.model.document_knowledge import (
    AssertionObject,
    EvidenceAnchor,
    NormativeForce,
)
from standards_atlas.domain.model.identifiers import ClauseId

DOCUMENT_KNOWLEDGE_PROPOSAL_SCHEMA_VERSION = 1
_IRI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")


def _require_absolute_iri(value: str, *, field_name: str) -> str:
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    scheme = urlsplit(value).scheme
    if not scheme or not _IRI_SCHEME.fullmatch(scheme):
        raise ValueError(f"{field_name} must be an absolute IRI")
    return value


def _validate_ontology_versions(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(value) != len(set(value)):
        raise ValueError("knowledge proposal ontology versions must be unique")
    for reference in value:
        if reference != reference.strip() or reference.count("@") != 1:
            raise ValueError(
                "knowledge proposal ontology versions must use '<id>@<version>' references"
            )
        ontology_id, version = reference.rsplit("@", 1)
        if (
            not ontology_id
            or not version
            or any(part.strip() != part for part in (ontology_id, version))
        ):
            raise ValueError(
                "knowledge proposal ontology versions must use '<id>@<version>' references"
            )
    return value


class KnowledgeProposalProvenance(BaseModel):
    """Run-level provenance for one document knowledge proposal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    extractor: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    model: str | None = None
    provider: str | None = None
    semantic_task: str | None = None
    prompt_version: str | None = None
    selection_reference: str | None = None


class KnowledgeProposalInput(BaseModel):
    """Direct lineage reference to one proposal consumed by a derived proposal run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_run_id: str = Field(min_length=1)
    proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_provenance: KnowledgeProposalProvenance

    @field_validator("proposal_run_id")
    @classmethod
    def run_id_has_no_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError(
                "knowledge proposal input run id must not contain surrounding whitespace"
            )
        return value


class KnowledgeEntityProposal(BaseModel):
    """One proposed ontology-grounded engineering entity.

    Proposal confidence and rationale are intentionally kept outside canonical
    ``KnowledgeEntity``. Adoption creates a separate accepted knowledge object.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    proposal_clause_ids: tuple[ClauseId, ...] = Field(min_length=1)
    class_iri: str = Field(min_length=1)
    normalized_label: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    source_anchor_ids: tuple[str, ...] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = Field(default=None, min_length=1)

    @field_validator("class_iri")
    @classmethod
    def class_iri_is_absolute(cls, value: str) -> str:
        return _require_absolute_iri(value, field_name="knowledge entity proposal class_iri")

    @model_validator(mode="after")
    def aliases_and_anchors_are_unique(self) -> KnowledgeEntityProposal:
        if len(self.proposal_clause_ids) != len(set(self.proposal_clause_ids)):
            raise ValueError("knowledge entity proposal source clauses must be unique")
        if len(self.aliases) != len(set(self.aliases)):
            raise ValueError("knowledge entity proposal aliases must be unique")
        if len(self.source_anchor_ids) != len(set(self.source_anchor_ids)):
            raise ValueError("knowledge entity proposal source anchors must be unique")
        return self


class NormativeAssertionProposal(BaseModel):
    """One proposed evidence-backed engineering assertion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    source_clause_id: ClauseId
    subject_id: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: AssertionObject
    normative_force: NormativeForce = NormativeForce.UNSPECIFIED
    evidence_anchor_ids: tuple[str, ...] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = Field(default=None, min_length=1)

    @field_validator("predicate")
    @classmethod
    def predicate_is_absolute(cls, value: str) -> str:
        return _require_absolute_iri(value, field_name="normative assertion proposal predicate")

    @model_validator(mode="after")
    def evidence_anchors_are_unique(self) -> NormativeAssertionProposal:
        if len(self.evidence_anchor_ids) != len(set(self.evidence_anchor_ids)):
            raise ValueError("normative assertion proposal evidence anchors must be unique")
        return self


class ProposalFailureKind(StrEnum):
    """Terminal reason a source clause produced no usable proposal."""

    TIMEOUT = "timeout"
    RESPONSE_ERROR = "response_error"
    UNAVAILABLE = "unavailable"
    VALIDATION_ERROR = "validation_error"


class ProposalAttemptStatus(StrEnum):
    """Outcome of one persisted proposal attempt."""

    OK = "ok"
    TIMEOUT = "timeout"
    RESPONSE_ERROR = "response_error"
    UNAVAILABLE = "unavailable"
    VALIDATION_ERROR = "validation_error"


class KnowledgeProposalViolationKind(StrEnum):
    """Non-fatal reason a proposed semantic item was rejected or left unresolved."""

    UNDECLARED_CLASS = "undeclared_class"
    UNDECLARED_PROPERTY = "undeclared_property"
    DUPLICATE_ENTITY_ID = "duplicate_entity_id"
    INVALID_ASSERTION = "invalid_assertion"
    UNRESOLVED_GROUNDING = "unresolved_grounding"
    AMBIGUOUS_GROUNDING = "ambiguous_grounding"


class KnowledgeProposalViolation(BaseModel):
    """Non-fatal proposal item that must not be adopted without correction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: ClauseId
    kind: KnowledgeProposalViolationKind
    term: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class KnowledgeProposalFailure(BaseModel):
    """Terminal non-fatal failure for one source clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: ClauseId
    kind: ProposalFailureKind
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)


class KnowledgeProposalAttempt(BaseModel):
    """One persisted proposal attempt, including retries and failures."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: ClauseId
    status: ProposalAttemptStatus
    duration_seconds: float = Field(ge=0.0)
    input_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    raw_response_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    error_type: str | None = None
    message: str | None = None

    @model_validator(mode="after")
    def status_matches_error_metadata(self) -> KnowledgeProposalAttempt:
        if self.status is ProposalAttemptStatus.OK and (
            self.error_type is not None or self.message is not None
        ):
            raise ValueError("successful knowledge proposal attempts cannot carry error metadata")
        if self.status is not ProposalAttemptStatus.OK and (
            not self.error_type or not self.message
        ):
            raise ValueError("failed knowledge proposal attempts require error_type and message")
        return self


class DocumentKnowledgeProposal(BaseModel):
    """Rebuildable, non-canonical proposal for one EngineeringDocument.

    The aggregate deliberately mirrors only the semantic shape needed for later
    qualification and adoption. Confidence, rationale, violations, attempts, failures
    and model provenance remain proposal metadata and therefore cannot become canonical merely
    by serializing this object.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = DOCUMENT_KNOWLEDGE_PROPOSAL_SCHEMA_VERSION
    proposal_run_id: str = Field(min_length=1)
    source_document_key: str = Field(min_length=1)
    ontology_versions: tuple[str, ...] = ()
    input_proposals: tuple[KnowledgeProposalInput, ...] = ()
    evidence_anchors: tuple[EvidenceAnchor, ...] = ()
    entity_proposals: tuple[KnowledgeEntityProposal, ...] = ()
    assertion_proposals: tuple[NormativeAssertionProposal, ...] = ()
    violations: tuple[KnowledgeProposalViolation, ...] = ()
    failures: tuple[KnowledgeProposalFailure, ...] = ()
    attempts: tuple[KnowledgeProposalAttempt, ...] = ()
    proposal_provenance: KnowledgeProposalProvenance

    @field_validator("schema_version", mode="before")
    @classmethod
    def schema_marker_is_exact_integer_one(cls, value: object) -> object:
        if type(value) is not int or value != DOCUMENT_KNOWLEDGE_PROPOSAL_SCHEMA_VERSION:
            raise ValueError(
                "unsupported document knowledge proposal schema version: "
                f"{value!r}; current is {DOCUMENT_KNOWLEDGE_PROPOSAL_SCHEMA_VERSION}"
            )
        return value

    @field_validator("proposal_run_id", "source_document_key")
    @classmethod
    def identifiers_have_no_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError(
                "knowledge proposal identifiers must not contain surrounding whitespace"
            )
        return value

    @field_validator("ontology_versions")
    @classmethod
    def ontology_versions_are_explicit_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_ontology_versions(value)

    @model_validator(mode="after")
    def references_are_local_and_resolved(self) -> DocumentKnowledgeProposal:
        if (self.entity_proposals or self.assertion_proposals) and not self.ontology_versions:
            raise ValueError("knowledge proposals with semantic terms require ontology_versions")

        input_run_ids = [item.proposal_run_id for item in self.input_proposals]
        if len(input_run_ids) != len(set(input_run_ids)):
            raise ValueError("knowledge proposal input run ids must be unique")
        if self.proposal_run_id in set(input_run_ids):
            raise ValueError("knowledge proposal cannot directly reference its own run as input")

        anchor_ids = [anchor.id for anchor in self.evidence_anchors]
        entity_ids = [entity.id for entity in self.entity_proposals]
        assertion_ids = [assertion.id for assertion in self.assertion_proposals]
        for label, values in (
            ("evidence anchor", anchor_ids),
            ("knowledge entity proposal", entity_ids),
            ("normative assertion proposal", assertion_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} ids must be unique")

        known_anchors = set(anchor_ids)
        known_entities = set(entity_ids)
        missing_entity_anchors = {
            anchor_id
            for entity in self.entity_proposals
            for anchor_id in entity.source_anchor_ids
            if anchor_id not in known_anchors
        }
        if missing_entity_anchors:
            raise ValueError(
                "knowledge entity proposals reference unknown evidence anchors: "
                f"{sorted(missing_entity_anchors)!r}"
            )

        missing_assertion_anchors = {
            anchor_id
            for assertion in self.assertion_proposals
            for anchor_id in assertion.evidence_anchor_ids
            if anchor_id not in known_anchors
        }
        if missing_assertion_anchors:
            raise ValueError(
                "normative assertion proposals reference unknown evidence anchors: "
                f"{sorted(missing_assertion_anchors)!r}"
            )

        missing_subjects = {
            assertion.subject_id
            for assertion in self.assertion_proposals
            if assertion.subject_id not in known_entities
        }
        if missing_subjects:
            raise ValueError(
                "normative assertion proposals reference unknown subjects: "
                f"{sorted(missing_subjects)!r}"
            )

        missing_objects = {
            assertion.object.entity_id
            for assertion in self.assertion_proposals
            if assertion.object.kind == "entity"
            and assertion.object.entity_id not in known_entities
        }
        if missing_objects:
            raise ValueError(
                "normative assertion proposals reference unknown objects: "
                f"{sorted(missing_objects)!r}"
            )

        failure_clause_ids = [failure.clause_id.value for failure in self.failures]
        if len(failure_clause_ids) != len(set(failure_clause_ids)):
            raise ValueError(
                "knowledge proposal may contain each terminal clause failure only once"
            )
        return self
