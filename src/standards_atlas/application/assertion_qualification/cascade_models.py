"""Schema-1 contracts for Slice-7B Efficient → Verify → Escalate qualification."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.domain.model import ClauseId

ASSERTION_QUALIFICATION_CASCADE_REPORT_SCHEMA_VERSION = 1


class AssertionVerificationDisposition(StrEnum):
    """Independent verifier decision for one efficient-stage candidate."""

    SUPPORTED = "supported"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


class AssertionCascadeRoute(StrEnum):
    """Deterministic route selected for one source clause."""

    EFFICIENT_ACCEPTED = "efficient_accepted"
    ESCALATED = "escalated"


class AssertionCascadeReason(StrEnum):
    """Machine-readable reason a clause left the efficient stage."""

    EFFICIENT_FAILURE = "efficient_failure"
    EFFICIENT_VIOLATION = "efficient_violation"
    VERIFICATION_ERROR = "verification_error"
    REJECTED_CANDIDATE = "rejected_candidate"
    UNCERTAIN_CANDIDATE = "uncertain_candidate"
    MISSING_ENTITY = "missing_entity"
    MISSING_ASSERTION = "missing_assertion"


class AssertionVerifierProvenance(BaseModel):
    """Run-level identity of the independent verification implementation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verifier: str = Field(min_length=1)
    verifier_version: str = Field(min_length=1)
    model: str | None = None
    provider: str | None = None
    prompt_version: str | None = None


class AssertionCandidateVerification(BaseModel):
    """Verifier disposition for one entity or assertion candidate ID."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(min_length=1)
    disposition: AssertionVerificationDisposition
    rationale: str | None = Field(default=None, min_length=1)


class AssertionClauseVerification(BaseModel):
    """Independent verification of one efficient-stage clause proposal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: ClauseId
    entity_reviews: tuple[AssertionCandidateVerification, ...] = ()
    assertion_reviews: tuple[AssertionCandidateVerification, ...] = ()
    missing_entity_detected: bool = False
    missing_assertion_detected: bool = False
    missing_rationale: str | None = Field(default=None, min_length=1)
    input_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    raw_response_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def review_ids_are_unique(self) -> AssertionClauseVerification:
        for label, reviews in (
            ("entity", self.entity_reviews),
            ("assertion", self.assertion_reviews),
        ):
            ids = [review.candidate_id for review in reviews]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} verification candidate ids must be unique")
        if (
            self.missing_entity_detected or self.missing_assertion_detected
        ) and self.missing_rationale is None:
            raise ValueError("missing-item detection requires missing_rationale")
        return self


class AssertionCascadeProposalSource(BaseModel):
    """Exact proposal artifact identity consumed or produced by one cascade stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: str = Field(pattern=r"^(efficient|escalation)$")
    proposal_run_id: str = Field(min_length=1)
    proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    extractor: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    model: str | None = None
    provider: str | None = None


class AssertionCascadeClauseReport(BaseModel):
    """Per-clause cascade route and verifier evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: ClauseId
    route: AssertionCascadeRoute
    reasons: tuple[AssertionCascadeReason, ...] = ()
    verification: AssertionClauseVerification | None = None
    verification_error_type: str | None = None
    verification_error_message: str | None = None
    efficient_entities: int = Field(ge=0)
    efficient_assertions: int = Field(ge=0)
    efficient_violations: int = Field(default=0, ge=0)
    efficient_failures: int = Field(default=0, ge=0)
    escalation_entities: int = Field(default=0, ge=0)
    escalation_assertions: int = Field(default=0, ge=0)
    escalation_violations: int = Field(default=0, ge=0)
    escalation_failures: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def route_and_evidence_are_consistent(self) -> AssertionCascadeClauseReport:
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("cascade clause reasons must be unique")
        if self.verification is not None and self.verification.clause_id != self.clause_id:
            raise ValueError("cascade verification must belong to the reported source clause")
        if self.efficient_failures and AssertionCascadeReason.EFFICIENT_FAILURE not in self.reasons:
            raise ValueError("efficient failures require efficient_failure escalation reason")
        if self.efficient_violations and (
            AssertionCascadeReason.EFFICIENT_VIOLATION not in self.reasons
        ):
            raise ValueError("efficient violations require efficient_violation escalation reason")
        if self.route is AssertionCascadeRoute.EFFICIENT_ACCEPTED:
            if self.reasons:
                raise ValueError("efficient-accepted clauses cannot carry escalation reasons")
            if self.verification is None:
                raise ValueError("efficient-accepted clauses require verifier evidence")
            if self.verification_error_type or self.verification_error_message:
                raise ValueError("efficient-accepted clauses cannot carry verifier errors")
            if any(
                (
                    self.escalation_entities,
                    self.escalation_assertions,
                    self.escalation_violations,
                    self.escalation_failures,
                )
            ):
                raise ValueError("efficient-accepted clauses cannot carry escalation results")
            if _verification_requires_escalation(self.verification):
                raise ValueError("efficient-accepted clauses must be fully supported")
        else:
            if not self.reasons:
                raise ValueError("escalated clauses require at least one escalation reason")
        if (self.verification_error_type is None) != (self.verification_error_message is None):
            raise ValueError("verification error type and message must be supplied together")
        if self.verification_error_type and (
            AssertionCascadeReason.VERIFICATION_ERROR not in self.reasons
        ):
            raise ValueError("verification errors require verification_error escalation reason")
        return self


class AssertionQualificationCascadeReport(SchemaBoundModel):
    """Threshold-free persisted record of one Efficient → Verify → Escalate run."""

    SCHEMA_FAMILY: ClassVar[str] = "assertion-qualification-cascade-report"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_QUALIFICATION_CASCADE_REPORT_SCHEMA_VERSION
    cascade_run_id: str = Field(min_length=1)
    source_document_key: str = Field(min_length=1)
    ontology_versions: tuple[str, ...] = Field(min_length=1)
    proposal_sources: tuple[AssertionCascadeProposalSource, ...] = Field(min_length=1)
    verifier_provenance: AssertionVerifierProvenance
    clauses: tuple[AssertionCascadeClauseReport, ...] = ()
    efficient_accepted_clauses: int = Field(ge=0)
    escalated_clauses: int = Field(ge=0)

    @field_validator("cascade_run_id", "source_document_key")
    @classmethod
    def identifiers_are_trimmed(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("cascade identifiers must not contain surrounding whitespace")
        return value

    @field_validator("ontology_versions")
    @classmethod
    def ontology_versions_are_explicit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("cascade ontology versions must be unique")
        for reference in value:
            if reference != reference.strip() or reference.count("@") != 1:
                raise ValueError("cascade ontology versions must use '<id>@<version>' references")
            ontology_id, version = reference.rsplit("@", 1)
            if not ontology_id or not version:
                raise ValueError("cascade ontology versions must use '<id>@<version>' references")
        return value

    @model_validator(mode="after")
    def run_identity_is_consistent(self) -> AssertionQualificationCascadeReport:
        clause_ids = [item.clause_id.value for item in self.clauses]
        if len(clause_ids) != len(set(clause_ids)):
            raise ValueError("cascade report clause ids must be unique")
        stages = [source.stage for source in self.proposal_sources]
        if len(stages) != len(set(stages)):
            raise ValueError("cascade proposal stages must be unique")
        run_ids = [source.proposal_run_id for source in self.proposal_sources]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("cascade proposal run ids must be unique")
        if "efficient" not in stages:
            raise ValueError("cascade report requires an efficient proposal source")
        accepted = sum(
            item.route is AssertionCascadeRoute.EFFICIENT_ACCEPTED for item in self.clauses
        )
        escalated = sum(item.route is AssertionCascadeRoute.ESCALATED for item in self.clauses)
        if self.efficient_accepted_clauses != accepted:
            raise ValueError("efficient accepted count does not match clause routes")
        if self.escalated_clauses != escalated:
            raise ValueError("escalated count does not match clause routes")
        has_escalation_source = "escalation" in stages
        if bool(escalated) != has_escalation_source:
            raise ValueError(
                "escalation proposal source must exist exactly when clauses were escalated"
            )
        return self


def _verification_requires_escalation(verification: AssertionClauseVerification) -> bool:
    reviews = (*verification.entity_reviews, *verification.assertion_reviews)
    return (
        verification.missing_entity_detected
        or verification.missing_assertion_detected
        or any(
            review.disposition is not AssertionVerificationDisposition.SUPPORTED
            for review in reviews
        )
    )
