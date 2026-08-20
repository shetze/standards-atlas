"""Manual review decisions for deterministic alignment results."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from standards_atlas.application.model.reference_candidates import CandidateRemainderKind


class OverrideAction(StrEnum):
    ASSIGN = "assign"
    IGNORE_CANDIDATE = "ignore_candidate"
    MARK_MISSING = "mark_missing"
    DEFINE_RANGE = "define_range"
    SET_REMAINDER_KIND = "set_remainder_kind"
    SET_FOLLOWING_LABEL = "set_following_label"
    SET_OBSERVED_HEADING = "set_observed_heading"
    SET_HEADING_LEVEL = "set_heading_level"


class OverrideBase(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: OverrideAction
    comment: str | None = None


class AssignOverride(OverrideBase):
    action: Literal[OverrideAction.ASSIGN] = OverrideAction.ASSIGN
    clause_id: str
    candidate_item_id: str


class IgnoreCandidateOverride(OverrideBase):
    action: Literal[OverrideAction.IGNORE_CANDIDATE] = OverrideAction.IGNORE_CANDIDATE
    candidate_item_id: str
    reason: str | None = None


class MarkMissingOverride(OverrideBase):
    action: Literal[OverrideAction.MARK_MISSING] = OverrideAction.MARK_MISSING
    clause_id: str


class DefineRangeOverride(OverrideBase):
    action: Literal[OverrideAction.DEFINE_RANGE] = OverrideAction.DEFINE_RANGE
    clause_id: str
    start_item_id: str
    end_item_id: str


class SetRemainderKindOverride(OverrideBase):
    action: Literal[OverrideAction.SET_REMAINDER_KIND] = OverrideAction.SET_REMAINDER_KIND
    candidate_item_id: str
    remainder_kind: CandidateRemainderKind


class SetFollowingLabelOverride(OverrideBase):
    action: Literal[OverrideAction.SET_FOLLOWING_LABEL] = OverrideAction.SET_FOLLOWING_LABEL
    candidate_item_id: str
    following_label_item_id: str


class SetObservedHeadingOverride(OverrideBase):
    action: Literal[OverrideAction.SET_OBSERVED_HEADING] = OverrideAction.SET_OBSERVED_HEADING
    clause_id: str
    heading: str | None = None


class SetHeadingLevelOverride(OverrideBase):
    action: Literal[OverrideAction.SET_HEADING_LEVEL] = OverrideAction.SET_HEADING_LEVEL
    clause_id: str
    level: int = Field(ge=1)


AlignmentOverride = Annotated[
    AssignOverride
    | IgnoreCandidateOverride
    | MarkMissingOverride
    | DefineRangeOverride
    | SetRemainderKindOverride
    | SetFollowingLabelOverride
    | SetObservedHeadingOverride
    | SetHeadingLevelOverride,
    Field(discriminator="action"),
]


class AlignmentOverrideDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    document_key: str
    source_alignment_hash: str | None = None
    overrides: tuple[AlignmentOverride, ...] = ()

    @field_validator("overrides", mode="before")
    @classmethod
    def normalize_empty_overrides(cls, value: object) -> object:
        return () if value is None else value


class OverrideValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["warning", "error"] = "error"
    override_index: int | None = Field(default=None, ge=0)
    message: str


class OverrideValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    valid: bool
    issues: tuple[OverrideValidationIssue, ...] = ()


class ReviewMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    created_at: datetime
    automatic_alignment_hash: str
    override_document_hash: str
    applied_overrides: int
    ignored_candidates: tuple[str, ...] = ()
