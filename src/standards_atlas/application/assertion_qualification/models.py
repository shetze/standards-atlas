"""Schema-1 contracts for assertion-centred golden suites and evaluation reports."""

from __future__ import annotations

import math
import re
import unicodedata
from enum import StrEnum
from typing import Annotated, ClassVar, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.domain.model import (
    AssertionObject,
    ClauseId,
    EvidenceSourceKind,
    NormativeForce,
)

ASSERTION_GOLDEN_SUITE_SCHEMA_VERSION = 1
ASSERTION_QUALIFICATION_REPORT_SCHEMA_VERSION = 1
ASSERTION_EVALUATION_CONTRACT = "assertion-clause-local-interim-v1"
_IRI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")


def _require_absolute_iri(value: str, *, field_name: str) -> str:
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    scheme = urlsplit(value).scheme
    if not scheme or not _IRI_SCHEME.fullmatch(scheme):
        raise ValueError(f"{field_name} must be an absolute IRI")
    return value


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def _validate_ontology_versions(value: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        raise ValueError("assertion golden suite requires at least one ontology version")
    if len(value) != len(set(value)):
        raise ValueError("assertion golden suite ontology versions must be unique")
    for reference in value:
        if reference != reference.strip() or reference.count("@") != 1:
            raise ValueError("ontology versions must use '<id>@<version>' references")
        ontology_id, version = reference.rsplit("@", 1)
        if not ontology_id or not version:
            raise ValueError("ontology versions must use '<id>@<version>' references")
    return value


class AssertionGoldenPartition(StrEnum):
    """Independent evaluation partition owned by one golden suite."""

    DEVELOPMENT = "development"
    HOLDOUT = "holdout"


class AssertionAuditBinding(BaseModel):
    """Identity of the unchanged completed review that published the suite."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: str = Field(min_length=1)
    review_version: str = Field(min_length=1)
    audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_fingerprint_contract: Literal["assertion-review-source-v1"] = (
        "assertion-review-source-v1"
    )


class GoldenKnowledgeEntity(BaseModel):
    """Expected ontology-grounded entity independent from runtime proposal IDs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    class_iri: str = Field(min_length=1)
    normalized_label: str = Field(min_length=1)

    @field_validator("class_iri")
    @classmethod
    def class_iri_is_absolute(cls, value: str) -> str:
        return _require_absolute_iri(value, field_name="golden entity class_iri")


class GoldenEvidenceSpan(BaseModel):
    """Exact expected grounding span in canonical clause plain text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document_key: str = Field(min_length=1)
    clause_id: ClauseId
    source_kind: EvidenceSourceKind
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def range_is_non_empty(self) -> GoldenEvidenceSpan:
        if self.end_offset <= self.start_offset:
            raise ValueError("golden evidence end_offset must be greater than start_offset")
        return self


class GoldenNormativeAssertion(BaseModel):
    """Expected relation, force and exact grounding for one source assertion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    source_clause_id: ClauseId
    subject_id: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: AssertionObject
    normative_force: NormativeForce = NormativeForce.UNSPECIFIED
    evidence: tuple[GoldenEvidenceSpan, ...] = Field(min_length=1)

    @field_validator("predicate")
    @classmethod
    def predicate_is_absolute(cls, value: str) -> str:
        return _require_absolute_iri(value, field_name="golden assertion predicate")

    @model_validator(mode="after")
    def evidence_is_local_to_source_clause(self) -> GoldenNormativeAssertion:
        if any(span.clause_id != self.source_clause_id for span in self.evidence):
            raise ValueError("golden assertion evidence must belong to its source clause")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("golden assertion evidence spans must be unique")
        return self


class AssertionGoldenCase(BaseModel):
    """Expected engineering knowledge for one immutable, case-local clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document_key: str = Field(min_length=1)
    clause_id: ClauseId
    reference: str = Field(min_length=1)
    canonical_reference: str = Field(min_length=1)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entities: tuple[GoldenKnowledgeEntity, ...] = ()
    assertions: tuple[GoldenNormativeAssertion, ...] = ()

    @property
    def case_key(self) -> tuple[str, str]:
        return (self.source_document_key, self.clause_id.value)

    @field_validator("source_document_key")
    @classmethod
    def document_key_has_no_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("golden source document key must not contain surrounding whitespace")
        return value

    @model_validator(mode="after")
    def assertion_references_are_local(self) -> AssertionGoldenCase:
        if any(item.source_clause_id != self.clause_id for item in self.assertions):
            raise ValueError("golden assertions must belong to their case clause")
        for assertion in self.assertions:
            if any(
                span.source_document_key != self.source_document_key for span in assertion.evidence
            ):
                raise ValueError("golden evidence must bind its case document")
        entity_ids = [entity.id for entity in self.entities]
        assertion_ids = [assertion.id for assertion in self.assertions]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("golden entity ids must be unique within a case")
        entity_signatures = [
            (_normalize_label(entity.normalized_label), entity.class_iri)
            for entity in self.entities
        ]
        if len(entity_signatures) != len(set(entity_signatures)):
            raise ValueError("golden entities must be semantically unique within a case")
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("golden assertion ids must be unique within a case")
        known_entities = set(entity_ids)
        missing_subjects = {
            assertion.subject_id
            for assertion in self.assertions
            if assertion.subject_id not in known_entities
        }
        if missing_subjects:
            raise ValueError(f"golden assertions reference unknown subjects: {missing_subjects!r}")
        missing_objects = {
            assertion.object.entity_id
            for assertion in self.assertions
            if assertion.object.kind == "entity"
            and assertion.object.entity_id not in known_entities
        }
        if missing_objects:
            raise ValueError(f"golden assertions reference unknown objects: {missing_objects!r}")
        return self


class AssertionGoldenSuite(SchemaBoundModel):
    """Versioned assertion golden suite for one independent evaluation partition."""

    SCHEMA_FAMILY: ClassVar[str] = "assertion-golden-suite"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_GOLDEN_SUITE_SCHEMA_VERSION
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    partition: AssertionGoldenPartition
    audit: AssertionAuditBinding
    ontology_versions: tuple[str, ...]
    cases: tuple[AssertionGoldenCase, ...] = Field(min_length=1)

    @field_validator("ontology_versions")
    @classmethod
    def ontology_versions_are_explicit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_ontology_versions(value)

    @model_validator(mode="after")
    def case_keys_are_unique(self) -> AssertionGoldenSuite:
        keys = [case.case_key for case in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("assertion golden suite case keys must be unique")
        return self


class CountMetrics(BaseModel):
    """Precision/recall counts for a multiset comparison."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected: int = Field(ge=0)
    predicted: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def counts_and_ratios_are_consistent(self) -> CountMetrics:
        if self.true_positive > min(self.expected, self.predicted):
            raise ValueError("true_positive cannot exceed expected or predicted counts")
        if self.false_positive != self.predicted - self.true_positive:
            raise ValueError("false_positive must equal predicted minus true_positive")
        if self.false_negative != self.expected - self.true_positive:
            raise ValueError("false_negative must equal expected minus true_positive")
        precision = (
            self.true_positive / self.predicted if self.predicted else float(self.expected == 0)
        )
        recall = self.true_positive / self.expected if self.expected else float(self.predicted == 0)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        for field_name, actual, expected in (
            ("precision", self.precision, precision),
            ("recall", self.recall, recall),
            ("f1", self.f1, f1),
        ):
            if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(f"{field_name} is inconsistent with qualification counts")
        return self


class AccuracyMetrics(BaseModel):
    """Accuracy for attributes evaluated only on aligned semantic items."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluated: int = Field(ge=0)
    correct: int = Field(ge=0)
    accuracy: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> AccuracyMetrics:
        if self.correct > self.evaluated:
            raise ValueError("accuracy correct count cannot exceed evaluated count")
        if self.evaluated == 0 and self.accuracy is not None:
            raise ValueError("accuracy must be None when no items were evaluated")
        if self.evaluated > 0 and self.accuracy is None:
            raise ValueError("accuracy is required when items were evaluated")
        if self.evaluated > 0 and self.accuracy is not None:
            expected = self.correct / self.evaluated
            if not math.isclose(self.accuracy, expected, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError("accuracy is inconsistent with evaluated/correct counts")
        return self


class NativeProposalProvenance(BaseModel):
    """Reference to an actually supplied full-document proposal source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["native_proposal"] = "native_proposal"
    proposal_run_id: str = Field(min_length=1)
    proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviewSnapshotProvenance(BaseModel):
    """Historical declarations are distinct from verified audit/snapshot content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["review_snapshot"] = "review_snapshot"
    audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_fingerprint_contract: Literal["assertion-review-snapshot-v1"] = (
        "assertion-review-snapshot-v1"
    )
    declared_proposal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_run_id: str = Field(min_length=1)
    cascade_run_id: str = Field(min_length=1)
    proposal_stage: Literal["efficient", "escalation"]
    route: Literal["efficient_accepted", "escalated"]
    reasons: tuple[str, ...] = ()
    verifier_dispositions: dict[str, str] = Field(default_factory=dict)
    missing_entity_detected: bool = False
    missing_assertion_detected: bool = False
    original_proposal_verification: Literal["unavailable"] = "unavailable"
    historical_model_provenance: Literal["unavailable"] = "unavailable"
    historical_input_provenance: Literal["unavailable"] = "unavailable"


type CandidateProvenance = Annotated[
    NativeProposalProvenance | ReviewSnapshotProvenance, Field(discriminator="kind")
]


class AssertionQualificationCaseReport(BaseModel):
    """Deterministic evaluation result for one golden clause case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document_key: str
    clause_id: ClauseId
    reference: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_status: Literal["present", "missing"]
    candidate_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provenance: CandidateProvenance | None = None
    entities: CountMetrics
    assertions: CountMetrics
    predicate_accuracy: AccuracyMetrics
    normative_force_accuracy: AccuracyMetrics
    grounding_accuracy: AccuracyMetrics
    exact_assertion_accuracy: AccuracyMetrics
    entity_false_positive_ids: tuple[str, ...] = ()
    entity_false_negative_ids: tuple[str, ...] = ()
    assertion_false_positive_ids: tuple[str, ...] = ()
    assertion_false_negative_ids: tuple[str, ...] = ()
    proposal_violations: int = Field(default=0, ge=0)
    proposal_failures: int = Field(default=0, ge=0)
    violation_details: tuple[str, ...] = ()
    failure_details: tuple[str, ...] = ()

    @property
    def case_key(self) -> tuple[str, str]:
        return (self.source_document_key, self.clause_id.value)

    @model_validator(mode="after")
    def input_identity_is_consistent(self) -> AssertionQualificationCaseReport:
        present = self.candidate_status == "present"
        if present != (self.provenance is not None) or present != (
            self.candidate_sha256 is not None
        ):
            raise ValueError("candidate status must match its provenance and fingerprint")
        if self.proposal_violations != len(self.violation_details):
            raise ValueError("proposal violation count must match retained details")
        if self.proposal_failures != len(self.failure_details):
            raise ValueError("proposal failure count must match retained details")
        return self


class AssertionQualificationAggregate(BaseModel):
    """Interim typed metrics across clauses; document count remains distinct."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    documents: int = Field(ge=1)
    clauses: int = Field(ge=1)
    candidate_clauses: int = Field(ge=0)
    entities: CountMetrics
    assertions: CountMetrics
    predicate_accuracy: AccuracyMetrics
    normative_force_accuracy: AccuracyMetrics
    grounding_accuracy: AccuracyMetrics
    exact_assertion_accuracy: AccuracyMetrics


class AssertionQualificationProposalSource(BaseModel):
    """Exact proposal artifact identity included in one evaluation report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document_key: str
    proposal_run_id: str
    proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    extractor: str
    extractor_version: str
    model: str | None = None
    provider: str | None = None
    prompt_version: str | None = None


class AssertionQualificationReport(SchemaBoundModel):
    """Reproducible metric report without an auto-adoption pass/fail policy."""

    SCHEMA_FAMILY: ClassVar[str] = "assertion-qualification-report"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_QUALIFICATION_REPORT_SCHEMA_VERSION
    evaluation_contract: Literal["assertion-clause-local-interim-v1"]
    candidate_mode: Literal["native_proposal", "review_snapshot"]
    audit: AssertionAuditBinding
    source_binding: Literal["golden_declared", "audit_verified"]
    golden_suite_id: str
    golden_suite_version: str
    golden_partition: AssertionGoldenPartition
    golden_suite_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ontology_versions: tuple[str, ...]
    proposal_sources: tuple[AssertionQualificationProposalSource, ...] = ()
    cases: tuple[AssertionQualificationCaseReport, ...] = Field(min_length=1)
    aggregate: AssertionQualificationAggregate

    @field_validator("ontology_versions")
    @classmethod
    def ontology_versions_are_explicit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_ontology_versions(value)

    @model_validator(mode="after")
    def report_identity_is_consistent(self) -> AssertionQualificationReport:
        if self.aggregate.clauses != len(self.cases):
            raise ValueError("aggregate clause count must match qualification cases")
        documents = {case.source_document_key for case in self.cases}
        if self.aggregate.documents != len(documents):
            raise ValueError("aggregate document count must match distinct documents")
        case_keys = [case.case_key for case in self.cases]
        if len(case_keys) != len(set(case_keys)):
            raise ValueError("qualification report case keys must be unique")
        if self.aggregate.candidate_clauses != sum(
            case.candidate_status == "present" for case in self.cases
        ):
            raise ValueError("aggregate candidate coverage must match cases")
        source_keys = [source.source_document_key for source in self.proposal_sources]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("qualification report proposal source keys must be unique")
        source_by_key = {source.source_document_key: source for source in self.proposal_sources}
        if not set(source_by_key) <= documents:
            raise ValueError("qualification report proposal sources must belong to report cases")
        if self.candidate_mode == "review_snapshot":
            if self.proposal_sources or self.source_binding != "audit_verified":
                raise ValueError(
                    "review snapshot reports require verified audit, not native sources"
                )
            if self.aggregate.candidate_clauses != self.aggregate.clauses:
                raise ValueError("review snapshot reports require complete candidate coverage")
        for case in self.cases:
            source = source_by_key.get(case.source_document_key)
            provenance = case.provenance
            if provenance is not None and provenance.kind != self.candidate_mode:
                raise ValueError("case provenance kind differs from report candidate mode")
            if isinstance(provenance, ReviewSnapshotProvenance):
                if provenance.audit_sha256 != self.audit.audit_sha256:
                    raise ValueError("snapshot provenance does not match report audit")
                continue
            if source is None:
                if provenance is not None:
                    raise ValueError("case proposal identity requires a proposal source entry")
                continue
            if provenance is None or (provenance.proposal_run_id, provenance.proposal_hash) != (
                source.proposal_run_id,
                source.proposal_hash,
            ):
                raise ValueError("case proposal identity does not match proposal source entry")
        for field_name in ("entities", "assertions"):
            total = getattr(self.aggregate, field_name)
            for counter in (
                "expected",
                "predicted",
                "true_positive",
                "false_positive",
                "false_negative",
            ):
                if getattr(total, counter) != sum(
                    getattr(getattr(case, field_name), counter) for case in self.cases
                ):
                    raise ValueError(f"aggregate {field_name}.{counter} differs from cases")
        for field_name in (
            "predicate_accuracy",
            "normative_force_accuracy",
            "grounding_accuracy",
            "exact_assertion_accuracy",
        ):
            total = getattr(self.aggregate, field_name)
            for counter in ("evaluated", "correct"):
                if getattr(total, counter) != sum(
                    getattr(getattr(case, field_name), counter) for case in self.cases
                ):
                    raise ValueError(f"aggregate {field_name}.{counter} differs from cases")
        return self
