"""Closed preparation contracts for applicability-presence HITL review."""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .model import Digest, EvidenceQuote, NonBlank, ReviewModel, ReviewPredicate


class HistoricalSignal(ReviewModel):
    artifact_sha256: Digest
    artifact_kind: Literal["golden", "review-suite", "consensus"]
    attribute: Literal["applicability_present"] = "applicability_present"
    status: Literal[
        "published", "proposed", "accepted", "unresolved", "conflict", "not_evaluated", "failed"
    ]
    predicate: ReviewPredicate | None = None
    model_values: dict[str, Any] = Field(default_factory=dict)
    stage: str | None = None
    context_binding: Literal["matched", "text-only"] = "text-only"
    reference_id: str | None = None

    @model_validator(mode="after")
    def no_default_labels(self):
        if self.status in {"not_evaluated", "failed"} and (
            self.predicate is not None or self.model_values
        ):
            raise ValueError("unobserved/failed history cannot supply values")
        return self


class HistoryArtifact(ReviewModel):
    location: NonBlank
    member: str | None = None
    sha256: Digest
    kind: NonBlank


class CandidateEntry(ReviewModel):
    example_id: NonBlank
    source_sha256: Digest
    document_key: NonBlank
    clause_type: NonBlank
    membership: Literal["development", "holdout", "candidate", "holdout-duplicate"]
    text_length: int = Field(ge=1, strict=True)
    priority: int = Field(ge=0, le=100, strict=True)
    reasons: tuple[str, ...]
    confirmed_attributes: tuple[str, ...] = ()
    historical_reference_attributes: tuple[str, ...] = ()
    disagreement_attributes: tuple[str, ...] = ()
    unresolved_attributes: tuple[str, ...] = ()
    technical_failure_count: int = Field(default=0, ge=0, strict=True)
    history: tuple[HistoricalSignal, ...] = ()


class CandidateIndex(ReviewModel):
    SCHEMA_FAMILY: ClassVar[str] = "review-candidates"
    schema_version: Literal[1] = 1
    kind: Literal["review-candidates"] = "review-candidates"
    package_sha256: Digest
    state_sha256: Digest
    population_sha256: Digest
    rules_sha256: Digest
    ranking_policy: Literal["review-priority-v1"] = "review-priority-v1"
    additional_development_budget: int = Field(default=20, ge=0, le=1000, strict=True)
    entries: tuple[CandidateEntry, ...]
    artifacts: tuple[HistoryArtifact, ...] = ()
    diagnostics: tuple[str, ...] = ()
    index_sha256: Digest


class SelectionItem(ReviewModel):
    example_id: NonBlank
    source_sha256: Digest
    priority: int = Field(ge=0, le=100, strict=True)
    rationale: NonBlank


class SelectionRequest(ReviewModel):
    actor: NonBlank
    model: NonBlank
    rationale: NonBlank
    additional_development_ids: tuple[NonBlank, ...] = ()
    priorities: tuple[SelectionItem, ...] = ()

    @model_validator(mode="after")
    def unique_items(self):
        if len(set(self.additional_development_ids)) != len(self.additional_development_ids):
            raise ValueError("duplicate additional Development id")
        keys = [item.example_id for item in self.priorities]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate selection priority")
        if not set(self.additional_development_ids) <= set(keys):
            raise ValueError("each additional Development case needs a bound priority/rationale")
        return self


class SelectionProposal(ReviewModel):
    SCHEMA_FAMILY: ClassVar[str] = "review-selection-proposal"
    schema_version: Literal[1] = 1
    kind: Literal["review-selection-proposal"] = "review-selection-proposal"
    package_sha256: Digest
    state_sha256: Digest
    index_sha256: Digest
    request: SelectionRequest
    review_order: tuple[str, ...]
    holdout_ids: tuple[str, ...]
    selection_sha256: Digest


class AnnotationRecommendation(ReviewModel):
    example_id: NonBlank
    source_sha256: Digest
    attribute: Literal["applicability_present"] = "applicability_present"
    predicate: ReviewPredicate
    rationale: NonBlank
    evidence: tuple[EvidenceQuote, ...] = ()


class AnnotationBatch(ReviewModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
    actor: NonBlank
    model: NonBlank
    recommendations: tuple[AnnotationRecommendation, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_annotations(self):
        keys = [(item.example_id, item.attribute) for item in self.recommendations]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate attribute recommendation in batch")
        return self
