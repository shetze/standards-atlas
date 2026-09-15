"""Workbench navigation/exposure metadata is not semantic review authority."""

from typing import Literal

from pydantic import Field, field_validator

from standards_atlas.application.semantic_qualification.review_package.model import (
    Assessment,
    Digest,
    HoldoutExposure,
    HumanDecisionInput,
    NonBlank,
    Reviewer,
    ReviewModel,
    WorkbenchState,
)

# Shared persistence contracts are imported from the applicability review package.
__all__ = [
    "Assessment",
    "BookmarkSubmission",
    "DecisionSubmission",
    "HoldoutExposure",
    "RevealSubmission",
    "Reviewer",
    "WorkbenchState",
]


class DecisionSubmission(ReviewModel):
    view_token: NonBlank
    human_attested: Literal[True]
    decisions: tuple[HumanDecisionInput, ...] = Field(min_length=1, max_length=32)

    @field_validator("human_attested", mode="before")
    @classmethod
    def explicit_human_attestation(cls, value):
        if value is not True:
            raise ValueError("explicit boolean true human review attestation is required")
        return value


class RevealSubmission(ReviewModel):
    view_token: NonBlank
    assessment: Assessment


class BookmarkSubmission(ReviewModel):
    reviewer: Reviewer
    example_id: NonBlank
    package_sha256: Digest
