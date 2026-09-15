"""Version-1 HITL review contracts for applicability presence.

The review layer deliberately contains only human-review state and source bindings. It
is not a compatibility surface for the removed clause-classification taxonomy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

import yaml
from jsonschema import Draft202012Validator
from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    StringConstraints,
    model_serializer,
    model_validator,
)

from standards_atlas.application.model.source_structure import SourceStructure
from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.schema.model import SchemaBoundModel

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Split = Literal["development", "holdout"]
REVIEW_ATTRIBUTE = "applicability_present"
REVIEW_ATTRIBUTES = (REVIEW_ATTRIBUTE,)


class ReviewModel(SchemaBoundModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ReviewPredicate(ReviewModel):
    """Exact applicability-presence decision."""

    equals: bool = Field(strict=True)

    @model_serializer
    def explicit_operator(self):
        return {"equals": self.equals}


class CoverageRequirement(ReviewModel):
    split: Split
    attribute: Literal["applicability_present"] = REVIEW_ATTRIBUTE
    minimum: int = Field(default=1, ge=1, strict=True)
    predicate: ReviewPredicate | None = None
    document_key: str | None = None
    clause_type: str | None = None


class ReviewProfile(ReviewModel):
    SCHEMA_FAMILY: ClassVar[str] = "review-profile"

    schema_version: Literal[1] = 1
    kind: Literal["review-profile"] = "review-profile"
    id: NonBlank = "applicability-presence-review-v1"
    version: NonBlank = "1.0.0"
    attributes: tuple[Literal["applicability_present"], ...] = REVIEW_ATTRIBUTES
    minimum_cases_per_split: int = Field(default=1, ge=1, strict=True)
    coverage: tuple[CoverageRequirement, ...] = ()

    @model_validator(mode="after")
    def valid_attributes(self):
        if self.attributes != REVIEW_ATTRIBUTES:
            raise ValueError("review profile is applicability-presence only")
        return self


class ReviewSourceSpec(ReviewModel):
    """Source declaration for building a review package; paths use project-root semantics."""

    SCHEMA_FAMILY: ClassVar[str] = "review-source-manifest"

    schema_version: Literal[1] = 1
    kind: Literal["review-source"] = "review-source"
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    run: Path | None = None
    dataset: Path | None = None
    golden: Path
    reference_suites: tuple[Path, ...] = ()
    seed: int = Field(default=20260913, strict=True)

    @model_validator(mode="after")
    def source_is_unique(self):
        if (self.run is None) == (self.dataset is None):
            raise ValueError("review source requires exactly one of run or dataset")
        return self

    @classmethod
    def load(cls, path: Path):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("review source manifest must contain a mapping")
        require_supported_schema("review-source-manifest", data.get("schema_version"))
        return cls.model_validate(data)


class ReviewSource(ReviewModel):
    example_id: NonBlank
    document_key: NonBlank
    clause_id: NonBlank
    reference: NonBlank
    text: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    structure: SourceStructure
    context_sha256: Digest
    source_sha256: Digest


class ReviewCase(ReviewModel):
    example_id: NonBlank
    split: Split
    attributes: tuple[Literal["applicability_present"], ...] = REVIEW_ATTRIBUTES
    selection_reasons: tuple[str, ...]


class ReviewPackage(ReviewModel):
    SCHEMA_FAMILY: ClassVar[str] = "review-package"

    schema_version: Literal[1] = 1
    kind: Literal["review-package"] = "review-package"
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    version: NonBlank = "1.0.0"
    created_at: AwareDatetime
    profile: ReviewProfile
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
    source_manifest: dict[str, str]
    input_files: dict[str, Digest]
    rules: dict[str, str]
    rules_sha256: Digest
    output_schema: dict[str, Any]
    package_sha256: Digest


class EvidenceQuote(ReviewModel):
    target: str = "text"
    quote: str = Field(min_length=1)
    prefix: str = ""
    suffix: str = ""
    purpose: Literal["support", "counterevidence", "context"] = "support"


class EvidenceSpan(EvidenceQuote):
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)


class ReviewProposal(ReviewModel):
    revision: int = Field(ge=1, strict=True)
    example_id: NonBlank
    attribute: Literal["applicability_present"] = REVIEW_ATTRIBUTE
    predicate: ReviewPredicate
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


class ReviewDecision(ReviewModel):
    revision: int = Field(ge=1, strict=True)
    example_id: NonBlank
    attribute: Literal["applicability_present"] = REVIEW_ATTRIBUTE
    status: Literal["confirmed", "corrected", "deferred", "rejected"]
    predicate: ReviewPredicate | None = None
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


class HumanDecisionInput(ReviewModel):
    example_id: NonBlank
    attribute: Literal["applicability_present"] = REVIEW_ATTRIBUTE
    status: Literal["confirmed", "corrected", "deferred", "rejected"]
    proposal_sha256: Digest | None = None
    predicate: ReviewPredicate | None = None
    comment: str = ""


class ReviewState(ReviewModel):
    SCHEMA_FAMILY: ClassVar[str] = "review-state"

    schema_version: Literal[1] = 1
    kind: Literal["review-state"] = "review-state"
    package_sha256: Digest
    revision: int = Field(default=0, ge=0, strict=True)
    proposals: tuple[ReviewProposal, ...] = ()
    decisions: tuple[ReviewDecision, ...] = ()
    state_sha256: Digest


def predicate_data(predicate: ReviewPredicate) -> dict:
    return {"equals": predicate.equals}


def validate_predicate(attribute: str, predicate: ReviewPredicate, schema: dict) -> None:
    if attribute != REVIEW_ATTRIBUTE or attribute not in schema.get("properties", {}):
        raise ValueError(f"unknown review attribute: {attribute}")
    value_schema = schema["properties"][attribute]
    errors = list(Draft202012Validator(value_schema).iter_errors(predicate.equals))
    if errors:
        raise ValueError(f"invalid review predicate for {attribute}: {errors[0].message}")


class ReviewReferenceCase(ReviewModel):
    example_id: NonBlank
    document_key: NonBlank
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    attributes: dict[Literal["applicability_present"], ReviewPredicate] = Field(min_length=1)


class ReviewReferenceSuite(ReviewModel):
    SCHEMA_FAMILY: ClassVar[str] = "review-reference-suite"

    schema_version: Literal[1] = 1
    kind: Literal["review-reference-suite"] = "review-reference-suite"
    id: NonBlank
    version: NonBlank
    split: Split
    status: Literal["draft", "published"] = "draft"
    reviewed_by: str | None = None
    review_reference: str | None = None
    cases: tuple[ReviewReferenceCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def review_and_uniqueness(self):
        if len({case.example_id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate review reference identity")
        if self.status == "published" and not (
            self.reviewed_by
            and self.reviewed_by.strip()
            and self.review_reference
            and self.review_reference.strip()
        ):
            raise ValueError("published review reference suite requires review provenance")
        return self


Reviewer = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Assessment = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)
]


class HoldoutExposure(ReviewModel):
    example_id: NonBlank
    reviewer: Reviewer
    assessment: Assessment
    source_sha256: Digest
    rules_sha256: Digest
    review_revision: int = Field(ge=0, strict=True)
    proposal_sha256s: tuple[Digest, ...]
    revealed_at: AwareDatetime


class WorkbenchState(ReviewModel):
    SCHEMA_FAMILY: ClassVar[str] = "review-workbench-state"

    schema_version: Literal[1] = 1
    kind: Literal["review-workbench-state"] = "review-workbench-state"
    package_sha256: Digest
    revision: int = Field(default=0, ge=0, strict=True)
    bookmarks: dict[str, str] = Field(default_factory=dict)
    exposures: tuple[HoldoutExposure, ...] = ()
    workbench_sha256: Digest


class WorkbenchEvidence(ReviewModel):
    SCHEMA_FAMILY: ClassVar[str] = "review-workbench-evidence"

    schema_version: Literal[1] = 1
    kind: Literal["review-workbench-evidence"] = "review-workbench-evidence"
    journal_present: bool = Field(strict=True)
    state: WorkbenchState
    history: tuple[WorkbenchState, ...] = ()
    audit_sha256: Digest


class ReviewPublication(ReviewModel):
    SCHEMA_FAMILY: ClassVar[str] = "review-publication"

    model_config = ConfigDict(revalidate_instances="always", extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    kind: Literal["review-publication"] = "review-publication"
    package: ReviewPackage
    state: ReviewState
    status: Literal["draft", "published"]
    holdout_declaration: NonBlank | None = None
    report: dict[str, Any]
    evidence_sha256: Digest
    workbench: WorkbenchEvidence
