"""Workbench navigation/exposure metadata is not semantic review authority."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator

from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    CampaignModel,
)
from standards_atlas.application.semantic_qualification.review_package.model import (
    Digest,
    HumanDecisionInput,
    NonBlank,
)

Reviewer = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Assessment = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)
]


class HoldoutExposure(CampaignModel):
    """One explicit reveal, with the prior human assessment and exactly exposed suggestions."""

    example_id: NonBlank
    reviewer: Reviewer
    assessment: Assessment
    source_sha256: Digest
    rules_sha256: Digest
    review_revision: int = Field(ge=0, strict=True)
    proposal_sha256s: tuple[Digest, ...]
    revealed_at: AwareDatetime


class WorkbenchState(CampaignModel):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["review-workbench-state"] = "review-workbench-state"
    package_sha256: Digest
    revision: int = Field(default=0, ge=0, strict=True)
    bookmarks: dict[str, str] = Field(default_factory=dict)
    exposures: tuple[HoldoutExposure, ...] = ()
    workbench_sha256: Digest


class DecisionSubmission(CampaignModel):
    view_token: NonBlank
    human_attested: Literal[True]
    decisions: tuple[HumanDecisionInput, ...] = Field(min_length=1, max_length=32)

    @field_validator("human_attested", mode="before")
    @classmethod
    def explicit_human_attestation(cls, value):
        if value is not True:
            raise ValueError("explicit boolean true human review attestation is required")
        return value


class RevealSubmission(CampaignModel):
    view_token: NonBlank
    assessment: Assessment


class BookmarkSubmission(CampaignModel):
    reviewer: Reviewer
    example_id: NonBlank
    package_sha256: Digest
