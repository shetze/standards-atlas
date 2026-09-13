"""Versioned review contracts. Suggestions never materialize human decisions."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from jsonschema import Draft202012Validator
from pydantic import AwareDatetime, Field, StringConstraints, model_serializer, model_validator

from standards_atlas.application.model.source_structure import SourceStructure
from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_ATTRIBUTES,
)
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    CampaignModel,
)
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    SemanticPredicate as SuitePredicate,
)

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Split = Literal["development", "holdout"]
CORE_ATTRIBUTES = (
    "primary_function",
    "primary_knowledge_kind",
    "role_semantics_present",
    "process_functions",
)


class SemanticPredicate(SuitePredicate):
    """Review persistence must retain exactly one operator, including explicit null."""

    must_be_empty: bool | None = Field(default=None, strict=True)

    @model_serializer
    def explicit_operator(self):
        return {key: getattr(self, key) for key in self.model_fields_set}


class CoverageRequirement(CampaignModel):
    """Optional predeclared class/negative/stratum coverage, not a post-hoc budget."""

    split: Split
    attribute: str
    minimum: int = Field(default=1, ge=1, strict=True)
    predicate: SemanticPredicate | None = None
    document_key: str | None = None
    clause_type: str | None = None


class ReviewProfile(CampaignModel):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["partial-review-profile"] = "partial-review-profile"
    id: NonBlank = "partial-semantic-reference-v1"
    version: NonBlank = "1.0.0"
    attributes: tuple[str, ...] = CORE_ATTRIBUTES
    minimum_cases_per_split: int = Field(default=1, ge=1, strict=True)
    coverage: tuple[CoverageRequirement, ...] = ()

    @model_validator(mode="after")
    def valid_attributes(self):
        if (
            len(set(self.attributes)) != len(self.attributes)
            or not set(CORE_ATTRIBUTES) <= set(self.attributes)
            or set(self.attributes) - set(PARTIAL_ATTRIBUTES)
        ):
            raise ValueError(
                "review attributes must be unique, current and include core dimensions"
            )
        if any(rule.attribute not in self.attributes for rule in self.coverage):
            raise ValueError("coverage rule must address a selected review attribute")
        return self


class ReviewSource(CampaignModel):
    example_id: NonBlank
    document_key: NonBlank
    clause_id: NonBlank
    reference: NonBlank
    text: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    structure: SourceStructure
    context_sha256: Digest
    source_sha256: Digest


class ReviewCase(CampaignModel):
    example_id: NonBlank
    split: Split
    attributes: tuple[str, ...]
    selection_reasons: tuple[str, ...]


class ReviewPackage(CampaignModel):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["partial-review-package"] = "partial-review-package"
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    version: NonBlank = "1.0.0"
    created_at: AwareDatetime
    profile: ReviewProfile
    # Source-only population allows replay of membership without labels or a live LLM.
    population: tuple[ReviewSource, ...] = Field(min_length=2)
    population_sha256: Digest
    cases: tuple[ReviewCase, ...] = Field(min_length=2)
    known_development_ids: tuple[str, ...]
    excluded_holdout_ids: tuple[str, ...]
    existing_holdout_ids: tuple[str, ...] = ()
    holdout_size: int = Field(ge=1, strict=True)
    seed: int = Field(strict=True)
    selection_method: Literal["source-stratified-disjoint-v1"] = "source-stratified-disjoint-v1"
    source_location: dict[str, str]
    campaign_manifest: dict[str, str]
    input_files: dict[str, Digest]
    # Exact task/schema/profile/instructions are frozen, not only a version string.
    rules: dict[str, str]
    rules_sha256: Digest
    output_schema: dict[str, Any]
    package_sha256: Digest


class EvidenceQuote(CampaignModel):
    target: str = "text"  # text or fact:<index> in this case's frozen SourceStructure
    quote: str = Field(min_length=1)
    prefix: str = ""
    suffix: str = ""
    purpose: Literal["support", "counterevidence", "context"] = "support"


class EvidenceSpan(EvidenceQuote):
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)


class ReviewProposal(CampaignModel):
    revision: int = Field(ge=1, strict=True)
    example_id: NonBlank
    attribute: NonBlank
    predicate: SemanticPredicate
    producer: NonBlank
    producer_kind: Literal["model", "historical", "engineering"]
    model: NonBlank | None = None
    rationale: NonBlank
    provenance: NonBlank
    created_at: AwareDatetime
    evidence: tuple[EvidenceSpan, ...] = ()
    proposal_sha256: Digest

    @model_validator(mode="after")
    def model_provenance(self):
        if self.producer_kind == "model" and self.model is None:
            raise ValueError("model proposals require an explicit model identity")
        return self


class ReviewDecision(CampaignModel):
    revision: int = Field(ge=1, strict=True)
    example_id: NonBlank
    attribute: NonBlank
    status: Literal["confirmed", "corrected", "deferred", "rejected"]
    predicate: SemanticPredicate | None = None
    proposal_sha256: Digest | None = None
    supersedes: Digest | None = None
    reviewer: NonBlank
    reviewed_at: AwareDatetime
    comment: str = ""
    decision_sha256: Digest

    @model_validator(mode="after")
    def explicit_decision(self):
        accepted = self.status in {"confirmed", "corrected"}
        if accepted != (self.predicate is not None):
            raise ValueError("only confirmed/corrected human decisions carry a predicate")
        if self.status in {"confirmed", "rejected"} and not self.proposal_sha256:
            raise ValueError("confirmation/rejection must identify a specific proposal revision")
        if (self.status == "corrected" or self.supersedes) and not self.comment.strip():
            raise ValueError("manual corrections and superseding reviews require a comment")
        return self


class HumanDecisionInput(CampaignModel):
    """Explicit human intent for one attribute; never a model submission contract."""

    example_id: NonBlank
    attribute: NonBlank
    status: Literal["confirmed", "corrected", "deferred", "rejected"]
    proposal_sha256: Digest | None = None
    predicate: SemanticPredicate | None = None
    comment: str = ""


class ReviewState(CampaignModel):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["partial-review-state"] = "partial-review-state"
    package_sha256: Digest
    revision: int = Field(default=0, ge=0, strict=True)
    proposals: tuple[ReviewProposal, ...] = ()
    decisions: tuple[ReviewDecision, ...] = ()
    state_sha256: Digest


def predicate_data(predicate: SuitePredicate) -> dict:
    """Keep explicit null, but never serialize unset alternative operators."""
    return predicate.model_dump(mode="json", exclude_unset=True)


def validate_predicate(attribute: str, predicate: SemanticPredicate, schema: dict) -> None:
    if attribute not in PARTIAL_ATTRIBUTES or attribute not in schema.get("properties", {}):
        raise ValueError(f"unknown review attribute: {attribute}")
    value_schema = schema["properties"][attribute]
    data = predicate_data(predicate)
    if "equals" in data:
        value = data["equals"]
    else:
        if value_schema.get("type") != "array":
            raise ValueError(f"collection predicate is invalid for {attribute}")
        value = data.get("must_include", [])
    errors = list(Draft202012Validator(value_schema).iter_errors(value))
    if errors:
        raise ValueError(f"invalid review predicate for {attribute}: {errors[0].message}")


class ReviewPublication(CampaignModel):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["partial-review-publication"] = "partial-review-publication"
    package: ReviewPackage
    state: ReviewState
    status: Literal["draft", "published"]
    holdout_declaration: NonBlank | None = None
    report: dict[str, Any]
    evidence_sha256: Digest
