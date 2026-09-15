"""Schema-1 contracts for Slice-7C assertion auto-adoption eligibility policy."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from standards_atlas.application.assertion_qualification.models import AssertionGoldenPartition
from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.domain.model import ClauseId, NormativeForce

ASSERTION_AUTO_ADOPTION_POLICY_SCHEMA_VERSION = 1
ASSERTION_AUTO_ADOPTION_REPORT_SCHEMA_VERSION = 1


def _validate_ontology_versions(value: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        raise ValueError("assertion auto-adoption policy requires ontology versions")
    if len(value) != len(set(value)):
        raise ValueError("assertion auto-adoption ontology versions must be unique")
    for reference in value:
        if reference != reference.strip() or reference.count("@") != 1:
            raise ValueError("ontology versions must use '<id>@<version>' references")
        ontology_id, version = reference.rsplit("@", 1)
        if not ontology_id or not version:
            raise ValueError("ontology versions must use '<id>@<version>' references")
    return value


class AssertionQualityThresholds(BaseModel):
    """Explicit quality gates for one golden partition.

    No quality ratio defaults are provided: enabling automatic eligibility requires a
    project-owned decision for every measured assertion-quality dimension.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_expected_entities: int = Field(default=1, ge=1)
    min_expected_assertions: int = Field(default=1, ge=1)
    min_entity_precision: float = Field(ge=0.0, le=1.0)
    min_entity_recall: float = Field(ge=0.0, le=1.0)
    min_assertion_precision: float = Field(ge=0.0, le=1.0)
    min_assertion_recall: float = Field(ge=0.0, le=1.0)
    min_predicate_accuracy: float = Field(ge=0.0, le=1.0)
    min_normative_force_accuracy: float = Field(ge=0.0, le=1.0)
    min_grounding_accuracy: float = Field(ge=0.0, le=1.0)
    min_exact_assertion_accuracy: float = Field(ge=0.0, le=1.0)
    max_entity_false_positives: int | None = Field(default=None, ge=0)
    max_entity_false_negatives: int | None = Field(default=None, ge=0)
    max_assertion_false_positives: int | None = Field(default=None, ge=0)
    max_assertion_false_negatives: int | None = Field(default=None, ge=0)
    max_proposal_violations: int = Field(default=0, ge=0)
    max_proposal_failures: int = Field(default=0, ge=0)


class AssertionAutoAdoptionPolicy(SchemaBoundModel):
    """Project-owned Development/Holdout gates for assertion auto-adoption eligibility."""

    SCHEMA_FAMILY: ClassVar[str] = "assertion-auto-adoption-policy"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_AUTO_ADOPTION_POLICY_SCHEMA_VERSION
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    ontology_versions: tuple[str, ...]
    development: AssertionQualityThresholds
    holdout: AssertionQualityThresholds

    @field_validator("id", "version")
    @classmethod
    def identifiers_are_trimmed(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("assertion auto-adoption policy identifiers must be trimmed")
        return value

    @field_validator("ontology_versions")
    @classmethod
    def ontology_versions_are_explicit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_ontology_versions(value)


class AssertionQualityGateOperator(StrEnum):
    """Comparison encoded in one persisted policy check."""

    GREATER_OR_EQUAL = "ge"
    LESS_OR_EQUAL = "le"


class AssertionQualityGateCheck(BaseModel):
    """One auditable threshold comparison."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str = Field(min_length=1)
    operator: AssertionQualityGateOperator
    observed: float | None
    threshold: float
    passed: bool

    @model_validator(mode="after")
    def comparison_is_consistent(self) -> AssertionQualityGateCheck:
        if self.observed is None:
            expected = False
        elif self.operator is AssertionQualityGateOperator.GREATER_OR_EQUAL:
            expected = self.observed >= self.threshold
        else:
            expected = self.observed <= self.threshold
        if self.passed is not expected:
            raise ValueError("quality gate check result is inconsistent with observed value")
        return self


class AssertionPartitionQualityGate(BaseModel):
    """Quality-gate result for one Development or Holdout qualification report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    partition: AssertionGoldenPartition
    golden_suite_id: str = Field(min_length=1)
    golden_suite_version: str = Field(min_length=1)
    golden_suite_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    qualification_report_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    passed: bool
    checks: tuple[AssertionQualityGateCheck, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def pass_flag_matches_checks(self) -> AssertionPartitionQualityGate:
        if self.passed is not all(check.passed for check in self.checks):
            raise ValueError("partition gate pass flag must match all threshold checks")
        return self


class AssertionProposalRuntimeIdentity(BaseModel):
    """Runtime identity that must stay stable between qualification and production."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    extractor: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    model: str | None = None
    provider: str | None = None
    prompt_version: str | None = None


class AssertionPipelineIdentityGate(BaseModel):
    """Check that Development, Holdout and production use one efficient-stage identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    development: AssertionProposalRuntimeIdentity | None = None
    holdout: AssertionProposalRuntimeIdentity | None = None
    production: AssertionProposalRuntimeIdentity
    passed: bool
    reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def result_is_consistent(self) -> AssertionPipelineIdentityGate:
        expected = (
            self.development is not None
            and self.holdout is not None
            and self.development == self.holdout == self.production
        )
        if self.passed is not expected:
            raise ValueError("pipeline identity gate result is inconsistent")
        if self.passed and self.reason is not None:
            raise ValueError("passed pipeline identity gate cannot carry a failure reason")
        if not self.passed and self.reason is None:
            raise ValueError("failed pipeline identity gate requires a reason")
        return self


class AssertionAutoAdoptionDisposition(StrEnum):
    """Slice-7C eligibility decision; this is not canonical adoption."""

    AUTO_ADOPTION_ELIGIBLE = "auto_adoption_eligible"
    REVIEW_REQUIRED = "review_required"


class AssertionAutoAdoptionReason(StrEnum):
    """Reason one effective assertion cannot be automatically adopted."""

    DEVELOPMENT_GATE_FAILED = "development_gate_failed"
    HOLDOUT_GATE_FAILED = "holdout_gate_failed"
    PIPELINE_IDENTITY_MISMATCH = "pipeline_identity_mismatch"
    ESCALATED_CLAUSE = "escalated_clause"
    ESCALATION_NOT_REVERIFIED = "escalation_not_reverified"
    NON_EXACT_GROUNDING = "non_exact_grounding"


class AssertionAutoAdoptionDecision(BaseModel):
    """Per-assertion eligibility decision consumed later by the Slice-8 adoption boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_stage: str = Field(pattern=r"^(efficient|escalation)$")
    proposal_run_id: str = Field(min_length=1)
    assertion_id: str = Field(min_length=1)
    source_clause_id: ClauseId
    predicate: str = Field(min_length=1)
    normative_force: NormativeForce
    required_entity_ids: tuple[str, ...] = Field(min_length=1)
    evidence_anchor_ids: tuple[str, ...] = Field(min_length=1)
    disposition: AssertionAutoAdoptionDisposition
    reasons: tuple[AssertionAutoAdoptionReason, ...] = ()

    @model_validator(mode="after")
    def decision_is_consistent(self) -> AssertionAutoAdoptionDecision:
        if len(self.required_entity_ids) != len(set(self.required_entity_ids)):
            raise ValueError("auto-adoption decision entity ids must be unique")
        if len(self.evidence_anchor_ids) != len(set(self.evidence_anchor_ids)):
            raise ValueError("auto-adoption decision evidence anchors must be unique")
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("auto-adoption decision reasons must be unique")
        if self.disposition is AssertionAutoAdoptionDisposition.AUTO_ADOPTION_ELIGIBLE:
            if self.source_stage != "efficient" or self.reasons:
                raise ValueError(
                    "auto-adoption-eligible assertions must be reason-free efficient candidates"
                )
        elif not self.reasons:
            raise ValueError("review-required assertions need at least one machine-readable reason")
        return self


class AssertionAutoAdoptionReport(SchemaBoundModel):
    """Reproducible Slice-7C gate and per-assertion eligibility result."""

    SCHEMA_FAMILY: ClassVar[str] = "assertion-auto-adoption-report"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_AUTO_ADOPTION_REPORT_SCHEMA_VERSION
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ontology_versions: tuple[str, ...]
    development_gate: AssertionPartitionQualityGate
    holdout_gate: AssertionPartitionQualityGate
    pipeline_identity_gate: AssertionPipelineIdentityGate
    qualification_gate_passed: bool
    cascade_run_id: str = Field(min_length=1)
    cascade_report_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_document_key: str = Field(min_length=1)
    efficient_proposal_run_id: str = Field(min_length=1)
    efficient_proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    escalation_proposal_run_id: str | None = None
    escalation_proposal_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    decisions: tuple[AssertionAutoAdoptionDecision, ...] = ()
    auto_adoption_eligible_assertions: int = Field(ge=0)
    review_required_assertions: int = Field(ge=0)
    efficient_accepted_clauses: int = Field(ge=0)
    escalated_clauses: int = Field(ge=0)

    @field_validator("ontology_versions")
    @classmethod
    def ontology_versions_are_explicit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_ontology_versions(value)

    @model_validator(mode="after")
    def report_counts_and_gate_are_consistent(self) -> AssertionAutoAdoptionReport:
        expected_gate = (
            self.development_gate.passed
            and self.holdout_gate.passed
            and self.pipeline_identity_gate.passed
        )
        if self.qualification_gate_passed is not expected_gate:
            raise ValueError(
                "qualification gate flag must match Development/Holdout/pipeline gates"
            )
        eligible = sum(
            item.disposition is AssertionAutoAdoptionDisposition.AUTO_ADOPTION_ELIGIBLE
            for item in self.decisions
        )
        review = len(self.decisions) - eligible
        if self.auto_adoption_eligible_assertions != eligible:
            raise ValueError("auto-adoption eligible count does not match assertion decisions")
        if self.review_required_assertions != review:
            raise ValueError("review-required count does not match assertion decisions")
        if not self.qualification_gate_passed and eligible:
            raise ValueError("failed qualification gate cannot yield auto-adoption eligibility")
        decision_ids = [
            (item.source_stage, item.proposal_run_id, item.assertion_id) for item in self.decisions
        ]
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("auto-adoption assertion decisions must be unique")
        if (self.escalation_proposal_run_id is None) != (self.escalation_proposal_hash is None):
            raise ValueError("escalation proposal run id and hash must be supplied together")
        return self
