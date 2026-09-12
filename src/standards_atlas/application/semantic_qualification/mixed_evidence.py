"""Sparse, attribute-specific acceptance contracts for the opt-in partial cascade.

These are not ModelVotes with default values. Deterministic decisions have no
numerical confidence or model support. A clause exit and a complete enrichment
are distinct, explicitly represented properties.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_ATTRIBUTES,
    PartialObservation,
    ordered_attributes,
)
from standards_atlas.application.semantic_qualification.taxonomy_decisions import (
    ClauseDecisionPlan,
    DecisionAttribute,
)

CORE_REQUIRED_ATTRIBUTES = (
    "primary_function",
    "primary_knowledge_kind",
    "applicability_present",
    "role_semantics_present",
)


class CompletionProfile(BaseModel):
    """Frozen denominator and required decisions, never the current question list."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: Literal["taxonomy-partial-completion-v1"] = "taxonomy-partial-completion-v1"
    required_attributes: tuple[DecisionAttribute, ...] = CORE_REQUIRED_ATTRIBUTES

    @model_validator(mode="after")
    def explicit_requirements(self) -> CompletionProfile:
        if not self.required_attributes:
            raise ValueError("at least one completion attribute is required")
        if ordered_attributes(self.required_attributes) != self.required_attributes:
            raise ValueError("completion attributes must be unique and canonically ordered")
        return self

    @property
    def benchmark_eligible(self) -> bool:
        """Focused experiments cannot count toward the 80% production target."""
        return set(CORE_REQUIRED_ATTRIBUTES).issubset(self.required_attributes)

    @property
    def fingerprint(self) -> str:
        return structure_fingerprint(self.model_dump(mode="json"))


class AttributeAcceptance(BaseModel):
    """One acceptance, its real support and its original accepting stage."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    attribute: DecisionAttribute
    status: Literal["accepted", "unresolved", "conflict", "not_evaluated"]
    value: Any = None
    proposed_value: Any = None
    source: Literal["deterministic", "models", "none"] = "none"
    stage: str | None = None
    rule: str | None = None
    category: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    # Model ids are provider:model identities, not attempts or repetitions.
    model_values: dict[str, Any] = Field(default_factory=dict)
    observed_model_count: int = Field(default=0, ge=0)
    supporting_models: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @model_validator(mode="after")
    def no_synthetic_evidence(self) -> AttributeAcceptance:
        if self.observed_model_count != len(self.model_values):
            raise ValueError("attribute participation must count its actual distinct models")
        if len(set(self.supporting_models)) != len(self.supporting_models) or not set(
            self.supporting_models
        ).issubset(self.model_values):
            raise ValueError("supporting models must be unique observed models")
        if self.status == "accepted":
            if self.source == "none" or not self.stage or not self.rule or self.reasons:
                raise ValueError("accepted attributes need a source, stage and rule, not blockers")
            if self.source == "models" and (not self.model_values or self.confidence is None):
                raise ValueError("model acceptance needs real attribute-specific support")
        elif self.value is not None:
            raise ValueError("unaccepted attributes cannot materialize semantic values")
        if self.source == "deterministic" and (
            self.model_values or self.supporting_models or self.confidence is not None
        ):
            raise ValueError("deterministic decisions cannot claim model votes or confidence")
        if self.status == "not_evaluated" and (self.model_values or self.source != "none"):
            raise ValueError("not evaluated is not an observed negative")
        return self

    @property
    def known(self) -> bool:
        return self.status == "accepted"


class MixedClauseConsensus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_contract: Literal["taxonomy-partial-v1"] = "taxonomy-partial-v1"
    example_id: str
    clause_id: str
    document_key: str
    reference: str
    heading: str | None = None
    content_hash: str
    decision_plan: ClauseDecisionPlan
    required_attributes: tuple[DecisionAttribute, ...]
    decisions: tuple[AttributeAcceptance, ...]
    # Pair inconsistencies may block a required primary without unfreezing it.
    consistency_reasons: tuple[str, ...] = ()
    resolution_sha256: str

    @model_validator(mode="after")
    def complete_accounting(self) -> MixedClauseConsensus:
        if tuple(item.attribute for item in self.decisions) != PARTIAL_ATTRIBUTES:
            raise ValueError("mixed consensus must account for all current attributes")
        CompletionProfile(required_attributes=self.required_attributes)
        source = self.decision_plan.source
        if (source.document_key, source.clause_id, source.content_hash) != (
            self.document_key,
            self.clause_id,
            self.content_hash,
        ):
            raise ValueError("mixed clause and source plan differ")
        return self

    def decision(self, attribute: str) -> AttributeAcceptance:
        return next(item for item in self.decisions if item.attribute == attribute)

    @property
    def escalation_reasons(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                [
                    f"{key}:{reason}"
                    for key in self.required_attributes
                    if not (item := self.decision(key)).known
                    for reason in (item.reasons or (item.status,))
                ]
                + list(self.consistency_reasons)
            )
        )

    @property
    def requires_review(self) -> bool:
        return bool(self.escalation_reasons)

    @property
    def review_reasons(self) -> tuple[str, ...]:
        return self.escalation_reasons

    @property
    def completed(self) -> bool:
        return not self.escalation_reasons

    @property
    def fully_evaluated(self) -> bool:
        return all(item.known for item in self.decisions)

    @property
    def accepted_values(self) -> dict[str, Any]:
        return {item.attribute: item.value for item in self.decisions if item.known}


class StagedPartialObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    stage: str
    model_id: str
    observation: PartialObservation
    applicability_eligible: bool = True


class MixedConsensusReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["mixed-consensus-report"] = "mixed-consensus-report"
    matrix_id: str
    corpus_id: str
    stage_id: str
    completion_profile: CompletionProfile
    selection_sha256: str
    resolution: dict[str, Any]
    consensus_policy: dict[str, Any]
    stage_model_count: int = Field(ge=0)
    source_rules_sha256: str
    previous_report_sha256: str | None = None
    clauses: tuple[MixedClauseConsensus, ...]

    @model_validator(mode="after")
    def consistent_profile(self) -> MixedConsensusReport:
        ids = [(item.document_key, item.clause_id) for item in self.clauses]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate mixed consensus coordinates")
        fingerprint = structure_fingerprint(self.resolution)
        for item in self.clauses:
            if item.required_attributes != self.completion_profile.required_attributes:
                raise ValueError("clause completion differs from the frozen profile")
            if item.resolution_sha256 != fingerprint:
                raise ValueError("clause routing policy differs from report")
            if item.decision_plan.rules_sha256 != self.source_rules_sha256:
                raise ValueError("clause rule profile differs from report")
        return self

    @property
    def fingerprint(self) -> str:
        return structure_fingerprint(self.model_dump(mode="json"))

    @property
    def clause_count(self) -> int:
        return len(self.clauses)

    @property
    def completed_count(self) -> int:
        return sum(item.completed for item in self.clauses)

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "selected_clause_count": self.clause_count,
            "accounted_clause_count": self.clause_count,
            "completed_clause_count": self.completed_count,
            "unresolved_clause_count": self.clause_count - self.completed_count,
            "fully_evaluated_clause_count": sum(item.fully_evaluated for item in self.clauses),
            "completion_rate": self.completed_count / self.clause_count if self.clauses else 0,
            "benchmark_eligible": self.completion_profile.benchmark_eligible,
            "attributes": {
                key: {
                    status: sum(item.decision(key).status == status for item in self.clauses)
                    for status in ("accepted", "unresolved", "conflict", "not_evaluated")
                }
                for key in PARTIAL_ATTRIBUTES
            },
        }
