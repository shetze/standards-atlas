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
ASSERTION_EVALUATION_CONTRACT = "assertion-clause-local-v1"
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


class MetricStatus(StrEnum):
    """Applicability/evaluability state carried with every ratio."""

    OK = "ok"
    NOT_APPLICABLE = "not_applicable"
    NOT_EVALUABLE = "not_evaluable"
    PARTIAL = "partial"


class RatioMetric(BaseModel):
    """One ratio with explicit numerator, denominator and null semantics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    value: float | None = Field(default=None, ge=0.0, le=1.0)
    status: MetricStatus

    @model_validator(mode="after")
    def ratio_is_consistent(self) -> RatioMetric:
        if self.numerator > self.denominator:
            raise ValueError("ratio numerator cannot exceed denominator")
        if self.denominator == 0:
            if self.value is not None:
                raise ValueError("zero-denominator ratios must have value=None")
            if self.status not in {MetricStatus.NOT_APPLICABLE, MetricStatus.NOT_EVALUABLE}:
                raise ValueError("zero-denominator ratio requires an explicit null status")
            return self
        if self.value is None:
            raise ValueError("non-zero denominator ratios require a value")
        expected = self.numerator / self.denominator
        if not math.isclose(self.value, expected, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("ratio value is inconsistent with numerator/denominator")
        if self.status not in {MetricStatus.OK, MetricStatus.PARTIAL}:
            raise ValueError("defined ratio requires ok or partial status")
        return self


class CountMetrics(BaseModel):
    """Strict multiset recognition metrics with explicit empty-denominator semantics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected: int = Field(ge=0)
    predicted: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: RatioMetric
    recall: RatioMetric
    f1: RatioMetric
    over_extraction: RatioMetric
    under_extraction: RatioMetric

    @model_validator(mode="after")
    def counts_and_ratios_are_consistent(self) -> CountMetrics:
        if self.true_positive > min(self.expected, self.predicted):
            raise ValueError("true_positive cannot exceed expected or predicted counts")
        if self.false_positive != self.predicted - self.true_positive:
            raise ValueError("false_positive must equal predicted minus true_positive")
        if self.false_negative != self.expected - self.true_positive:
            raise ValueError("false_negative must equal expected minus true_positive")
        expected_ratios = (
            (self.precision, self.true_positive, self.predicted, MetricStatus.NOT_APPLICABLE),
            (self.recall, self.true_positive, self.expected, MetricStatus.NOT_APPLICABLE),
            (
                self.f1,
                2 * self.true_positive,
                self.expected + self.predicted,
                MetricStatus.NOT_APPLICABLE,
            ),
            (
                self.over_extraction,
                self.false_positive,
                self.predicted,
                MetricStatus.NOT_APPLICABLE,
            ),
            (
                self.under_extraction,
                self.false_negative,
                self.expected,
                MetricStatus.NOT_APPLICABLE,
            ),
        )
        for ratio, numerator, denominator, empty_status in expected_ratios:
            if (ratio.numerator, ratio.denominator) != (numerator, denominator):
                raise ValueError("count metric ratio support is inconsistent with counts")
            if denominator == 0 and ratio.status is not empty_status:
                raise ValueError("count metric empty denominator must be not_applicable")
        return self


class AccuracyMetrics(BaseModel):
    """Attribute accuracy over deterministic one-to-one alignments."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    support_expected: int = Field(ge=0)
    support_predicted: int = Field(ge=0)
    evaluated: int = Field(ge=0)
    correct: int = Field(ge=0)
    ambiguous_expected: int = Field(default=0, ge=0)
    ambiguous_predicted: int = Field(default=0, ge=0)
    unmatched_expected: int = Field(default=0, ge=0)
    unmatched_predicted: int = Field(default=0, ge=0)
    accuracy: RatioMetric
    alignment_coverage: RatioMetric

    @model_validator(mode="after")
    def counts_are_consistent(self) -> AccuracyMetrics:
        if self.correct > self.evaluated:
            raise ValueError("accuracy correct count cannot exceed evaluated count")
        if self.support_expected != (
            self.evaluated + self.ambiguous_expected + self.unmatched_expected
        ):
            raise ValueError("expected alignment support is inconsistent")
        if self.support_predicted != (
            self.evaluated + self.ambiguous_predicted + self.unmatched_predicted
        ):
            raise ValueError("predicted alignment support is inconsistent")
        if (self.accuracy.numerator, self.accuracy.denominator) != (
            self.correct,
            self.evaluated,
        ):
            raise ValueError("accuracy ratio support is inconsistent")
        if (self.alignment_coverage.numerator, self.alignment_coverage.denominator) != (
            self.evaluated,
            self.support_expected,
        ):
            raise ValueError("alignment coverage support is inconsistent")
        return self


class ComparisonAlignmentStatus(StrEnum):
    """Strict/diagnostic alignment state without semantic guessing."""

    MATCHED = "matched"
    EXPECTED_ONLY = "expected_only"
    CANDIDATE_ONLY = "candidate_only"
    AMBIGUOUS = "ambiguous"


class ComparisonAlignmentRecord(BaseModel):
    """Auditable bucket record for strict identity or diagnostic attribute alignment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document_key: str = Field(min_length=1)
    clause_id: ClauseId
    rule: Literal[
        "entity_label_identity",
        "assertion_endpoint_identity",
        "assertion_relation_identity",
    ]
    status: ComparisonAlignmentStatus
    golden_ids: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def alignment_state_is_consistent(self) -> ComparisonAlignmentRecord:
        if not self.golden_ids and not self.candidate_ids:
            raise ValueError("alignment record must reference at least one object")
        if self.status is ComparisonAlignmentStatus.MATCHED:
            if len(self.golden_ids) != 1 or len(self.candidate_ids) != 1:
                raise ValueError("matched alignment requires exactly one object on each side")
        elif self.status is ComparisonAlignmentStatus.EXPECTED_ONLY:
            if not self.golden_ids or self.candidate_ids:
                raise ValueError("expected-only alignment has candidates")
        elif self.status is ComparisonAlignmentStatus.CANDIDATE_ONLY:
            if self.golden_ids or not self.candidate_ids:
                raise ValueError("candidate-only alignment has golden objects")
        elif not self.golden_ids or not self.candidate_ids:
            raise ValueError("ambiguous alignment requires objects on both sides")
        return self


class AssertionDiagnosticCode(StrEnum):
    """Controlled AP01 diagnostic vocabulary; codes do not imply human confirmation."""

    MISSING_WORK_PRODUCT = "missing_work_product"
    WRONG_ENTITY_CLASS = "wrong_entity_class"
    OVER_EXTRACTED_DETAIL = "over_extracted_detail"
    NOTE_OVER_EXTRACTION = "note_over_extraction"
    LIST_OVER_ATOMIZATION = "list_over_atomization"
    MISSING_ASSERTION = "missing_assertion"
    INVENTED_ASSERTION = "invented_assertion"
    WRONG_PREDICATE = "wrong_predicate"
    WRONG_NORMATIVE_FORCE = "wrong_normative_force"
    WRONG_CONTEXT_USE = "wrong_context_use"
    GROUNDING_FAILURE = "grounding_failure"
    CONDITIONAL_SEMANTICS_LOSS = "conditional_semantics_loss"
    UNCLASSIFIED_SEMANTIC_MISMATCH = "unclassified_semantic_mismatch"


class AssertionDiagnosticOrigin(StrEnum):
    STRICT_COMPARISON = "strict_comparison"
    EVIDENCE_INTEGRITY = "evidence_integrity"
    PROPOSAL_DIAGNOSTIC = "proposal_diagnostic"
    HUMAN_ANNOTATION = "human_annotation"


class AssertionDiagnosticStatus(StrEnum):
    RULE_BASED = "rule_based"
    NEEDS_REVIEW = "needs_review"
    HUMAN_CONFIRMED = "human_confirmed"


class AssertionQualificationFinding(BaseModel):
    """One traceable diagnosis derived from a difference or retained diagnostic."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document_key: str = Field(min_length=1)
    clause_id: ClauseId
    codes: tuple[AssertionDiagnosticCode, ...] = Field(min_length=1)
    golden_ids: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    violation_reference: str | None = None
    observed_difference: str = Field(min_length=1)
    rule: str = Field(min_length=1)
    origin: AssertionDiagnosticOrigin
    status: AssertionDiagnosticStatus
    human_annotation_id: str | None = None

    @model_validator(mode="after")
    def diagnosis_state_is_explicit(self) -> AssertionQualificationFinding:
        if len(self.codes) != len(set(self.codes)):
            raise ValueError("diagnostic finding codes must be unique")
        if not self.golden_ids and not self.candidate_ids and self.violation_reference is None:
            raise ValueError("diagnostic finding requires an object or violation reference")
        confirmed = self.status is AssertionDiagnosticStatus.HUMAN_CONFIRMED
        if confirmed != (self.origin is AssertionDiagnosticOrigin.HUMAN_ANNOTATION):
            raise ValueError("human-confirmed diagnostics require human annotation origin")
        if confirmed != (self.human_annotation_id is not None):
            raise ValueError("human-confirmed diagnostics require an annotation id")
        return self


class EvidenceIntegrityStatus(StrEnum):
    """Technical result for one candidate evidence use."""

    VALID = "valid"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    CONFLICTING = "conflicting"


class EvidenceIntegrityFinding(BaseModel):
    """One evidence use resolved only against frozen source surfaces."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_kind: Literal["entity", "assertion"]
    owner_id: str = Field(min_length=1)
    anchor_id: str = Field(min_length=1)
    source_document_key: str = Field(min_length=1)
    source_clause_id: str = Field(min_length=1)
    source_kind: EvidenceSourceKind
    status: EvidenceIntegrityStatus
    reason: str = Field(min_length=1)


class EvidenceIntegrityMetrics(BaseModel):
    """Technical source-surface integrity, separate from expected-span equality."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total: int = Field(ge=0)
    checked: int = Field(ge=0)
    valid: int = Field(ge=0)
    invalid: int = Field(ge=0)
    unavailable: int = Field(ge=0)
    conflicting: int = Field(ge=0)
    validity: RatioMetric

    @model_validator(mode="after")
    def counts_are_consistent(self) -> EvidenceIntegrityMetrics:
        if self.checked != self.valid + self.invalid:
            raise ValueError("evidence checked count must equal valid plus invalid")
        if self.total != self.checked + self.unavailable + self.conflicting:
            raise ValueError("evidence integrity counts do not sum to total")
        if (self.validity.numerator, self.validity.denominator) != (self.valid, self.checked):
            raise ValueError("evidence validity ratio support is inconsistent")
        return self


class SemanticEvidenceMetrics(BaseModel):
    """AP01 does not infer semantic evidence strength from technical integrity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["not_evaluated"] = "not_evaluated"
    evaluated: Literal[0] = 0
    value: None = None


class CaseExactMatchStatus(StrEnum):
    EXACT = "exact"
    MISMATCH = "mismatch"
    MISSING_CANDIDATE = "missing_candidate"


class CaseExactMatch(BaseModel):
    """Exact equality of the fields actually annotated by the golden case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: bool | None
    status: CaseExactMatchStatus

    @model_validator(mode="after")
    def value_matches_status(self) -> CaseExactMatch:
        expected = {
            CaseExactMatchStatus.EXACT: True,
            CaseExactMatchStatus.MISMATCH: False,
            CaseExactMatchStatus.MISSING_CANDIDATE: None,
        }[self.status]
        if self.value is not expected:
            raise ValueError("clause exact-match value differs from status")
        return self


class ClauseExactMatchAggregate(BaseModel):
    """Clause-level exact match with missing candidate coverage kept visible."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: int = Field(ge=1)
    candidate_cases: int = Field(ge=0)
    matched: int = Field(ge=0)
    missing_candidates: int = Field(ge=0)
    accuracy: RatioMetric

    @model_validator(mode="after")
    def counts_are_consistent(self) -> ClauseExactMatchAggregate:
        if self.candidate_cases + self.missing_candidates != self.cases:
            raise ValueError("clause exact-match coverage differs from total cases")
        if self.matched > self.candidate_cases:
            raise ValueError("clause exact-match matches exceed candidate cases")
        if (self.accuracy.numerator, self.accuracy.denominator) != (self.matched, self.cases):
            raise ValueError("clause exact-match ratio support is inconsistent")
        return self


class OntologyResourceBinding(BaseModel):
    """Exact packaged ontology resource bytes used for hierarchy-dependent metrics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: str = Field(min_length=1)
    ontology_iri: str = Field(min_length=1)
    version_iri: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    resource_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def reference_is_explicit(self) -> OntologyResourceBinding:
        if self.reference.count("@") != 1:
            raise ValueError("ontology resource reference must use '<id>@<version>'")
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
    """Deterministic comparison result for one golden clause case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document_key: str
    clause_id: ClauseId
    reference: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_status: Literal["present", "missing"]
    candidate_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provenance: CandidateProvenance | None = None
    entities: CountMetrics
    typed_entities: CountMetrics
    entity_class_accuracy: AccuracyMetrics
    work_product_precision: RatioMetric
    work_product_recall: RatioMetric
    work_product_class_accuracy: AccuracyMetrics
    required_work_product_relation_recall: RatioMetric
    assertions: CountMetrics
    predicate_accuracy: AccuracyMetrics
    normative_force_accuracy: AccuracyMetrics
    evidence_integrity: EvidenceIntegrityMetrics
    evidence_span_exact_match: AccuracyMetrics
    semantic_evidence: SemanticEvidenceMetrics
    exact_assertion_accuracy: AccuracyMetrics
    clause_exact_match: CaseExactMatch
    entity_alignment: tuple[ComparisonAlignmentRecord, ...] = ()
    assertion_endpoint_alignment: tuple[ComparisonAlignmentRecord, ...] = ()
    assertion_relation_alignment: tuple[ComparisonAlignmentRecord, ...] = ()
    evidence_integrity_findings: tuple[EvidenceIntegrityFinding, ...] = ()
    diagnostic_findings: tuple[AssertionQualificationFinding, ...] = ()
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
        if len(self.evidence_integrity_findings) != self.evidence_integrity.total:
            raise ValueError("evidence integrity findings must match evidence total")
        if any(
            (finding.source_document_key, finding.clause_id.value) != self.case_key
            for finding in self.diagnostic_findings
        ):
            raise ValueError("diagnostic finding belongs to a different qualification case")
        for records in (
            self.entity_alignment,
            self.assertion_endpoint_alignment,
            self.assertion_relation_alignment,
        ):
            if any(
                (record.source_document_key, record.clause_id.value) != self.case_key
                for record in records
            ):
                raise ValueError("alignment record belongs to a different qualification case")
        return self


class AssertionQualificationAggregate(BaseModel):
    """Dimensionally separated metrics across clause-local cases."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    documents: int = Field(ge=1)
    clauses: int = Field(ge=1)
    candidate_clauses: int = Field(ge=0)
    entities: CountMetrics
    typed_entities: CountMetrics
    entity_class_accuracy: AccuracyMetrics
    work_product_precision: RatioMetric
    work_product_recall: RatioMetric
    work_product_class_accuracy: AccuracyMetrics
    required_work_product_relation_recall: RatioMetric
    assertions: CountMetrics
    predicate_accuracy: AccuracyMetrics
    normative_force_accuracy: AccuracyMetrics
    evidence_integrity: EvidenceIntegrityMetrics
    evidence_span_exact_match: AccuracyMetrics
    semantic_evidence: SemanticEvidenceMetrics
    exact_assertion_accuracy: AccuracyMetrics
    clause_exact_match: ClauseExactMatchAggregate


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
    """Reproducible dimensional report without an auto-adoption pass/fail flag."""

    SCHEMA_FAMILY: ClassVar[str] = "assertion-qualification-report"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_QUALIFICATION_REPORT_SCHEMA_VERSION
    evaluation_contract: Literal["assertion-clause-local-v1"]
    candidate_mode: Literal["native_proposal", "review_snapshot"]
    audit: AssertionAuditBinding
    source_binding: Literal["golden_declared", "audit_verified"]
    golden_suite_id: str
    golden_suite_version: str
    golden_partition: AssertionGoldenPartition
    golden_suite_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ontology_versions: tuple[str, ...]
    ontology_resources: tuple[OntologyResourceBinding, ...]
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
        resource_refs = tuple(item.reference for item in self.ontology_resources)
        if resource_refs != self.ontology_versions:
            raise ValueError("ontology resource bindings must match ordered ontology versions")
        if len(resource_refs) != len(set(resource_refs)):
            raise ValueError("ontology resource bindings must be unique")
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
        for field_name in ("entities", "typed_entities", "assertions"):
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
            "entity_class_accuracy",
            "work_product_class_accuracy",
            "predicate_accuracy",
            "normative_force_accuracy",
            "evidence_span_exact_match",
            "exact_assertion_accuracy",
        ):
            total = getattr(self.aggregate, field_name)
            for counter in (
                "support_expected",
                "support_predicted",
                "evaluated",
                "correct",
                "ambiguous_expected",
                "ambiguous_predicted",
                "unmatched_expected",
                "unmatched_predicted",
            ):
                if getattr(total, counter) != sum(
                    getattr(getattr(case, field_name), counter) for case in self.cases
                ):
                    raise ValueError(f"aggregate {field_name}.{counter} differs from cases")
        for field_name in (
            "work_product_precision",
            "work_product_recall",
            "required_work_product_relation_recall",
        ):
            total = getattr(self.aggregate, field_name)
            if total.numerator != sum(getattr(case, field_name).numerator for case in self.cases):
                raise ValueError(f"aggregate {field_name}.numerator differs from cases")
            if total.denominator != sum(
                getattr(case, field_name).denominator for case in self.cases
            ):
                raise ValueError(f"aggregate {field_name}.denominator differs from cases")
        evidence = self.aggregate.evidence_integrity
        for counter in ("total", "checked", "valid", "invalid", "unavailable", "conflicting"):
            if getattr(evidence, counter) != sum(
                getattr(case.evidence_integrity, counter) for case in self.cases
            ):
                raise ValueError(f"aggregate evidence_integrity.{counter} differs from cases")
        if self.aggregate.clause_exact_match.cases != len(self.cases):
            raise ValueError("aggregate clause exact-match case count differs from report")
        if self.aggregate.clause_exact_match.candidate_cases != self.aggregate.candidate_clauses:
            raise ValueError("aggregate clause exact-match coverage differs from candidates")
        return self
