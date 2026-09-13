"""Closed preparation contracts. Agent recommendations are never human decisions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    CampaignModel,
)

from .model import Digest, EvidenceQuote, NonBlank, SemanticPredicate


class HistoricalSignal(CampaignModel):
    """A source-bound report item, not a freshly verified model call or HITL decision."""

    artifact_sha256: Digest
    artifact_kind: Literal["golden", "semantic-suite", "mixed", "consensus", "observation"]
    attribute: NonBlank
    status: Literal[
        "published",
        "proposed",
        "accepted",
        "observed",
        "unresolved",
        "conflict",
        "not_evaluated",
        "failed",
    ]
    predicate: SemanticPredicate | None = None
    model_values: dict[str, Any] = Field(default_factory=dict)
    stage: str | None = None
    context_binding: Literal["matched", "text-only"] = "text-only"
    # Informational provenance; never converted into ReviewDecision by this reader.
    reference_id: str | None = None

    @model_validator(mode="after")
    def no_default_labels(self):
        if self.status in {"not_evaluated", "failed"} and (
            self.predicate is not None or self.model_values
        ):
            raise ValueError("unobserved/failed history cannot supply semantic values")
        return self


class HistoryArtifact(CampaignModel):
    location: NonBlank
    member: str | None = None
    sha256: Digest
    kind: NonBlank


class CandidateEntry(CampaignModel):
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


class CandidateIndex(CampaignModel):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["partial-review-candidates"] = "partial-review-candidates"
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


class SelectionItem(CampaignModel):
    example_id: NonBlank
    source_sha256: Digest
    priority: int = Field(ge=0, le=100, strict=True)
    rationale: NonBlank


class SelectionRequest(CampaignModel):
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


class SelectionProposal(CampaignModel):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["partial-review-selection-proposal"] = "partial-review-selection-proposal"
    package_sha256: Digest
    state_sha256: Digest
    index_sha256: Digest
    request: SelectionRequest
    # Replayable total order, not the transient order of a model response or filesystem.
    review_order: tuple[str, ...]
    holdout_ids: tuple[str, ...]
    selection_sha256: Digest


class AnnotationRecommendation(CampaignModel):
    example_id: NonBlank
    source_sha256: Digest
    attribute: NonBlank
    predicate: SemanticPredicate
    rationale: NonBlank
    evidence: tuple[EvidenceQuote, ...] = ()


class AnnotationBatch(CampaignModel):
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
