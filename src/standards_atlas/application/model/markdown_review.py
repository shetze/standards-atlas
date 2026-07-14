"""Models for full-document Markdown alignment review."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MarkdownReviewChangeKind(StrEnum):
    ADD_ALIGNMENT = "add_alignment"
    REMOVE_ALIGNMENT = "remove_alignment"
    CHANGE_REFERENCE = "change_reference"
    CHANGE_HEADING = "change_heading"
    CHANGE_LEVEL = "change_level"
    CONTENT_MODIFIED = "content_modified"


class MarkdownReviewHeading(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: int = Field(ge=1)
    reference: str
    heading: str | None = None
    trailing_content: str | None = None


class MarkdownReviewBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_id: str
    heading: MarkdownReviewHeading | None = None
    disabled_heading_text: str | None = None
    body: str = ""


class MarkdownReviewDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    blocks: tuple[MarkdownReviewBlock, ...] = ()


class MarkdownReviewChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: MarkdownReviewChangeKind
    item_id: str
    reference: str | None = None
    previous_reference: str | None = None
    heading: str | None = None
    previous_heading: str | None = None
    level: int | None = Field(default=None, ge=1)
    previous_level: int | None = Field(default=None, ge=1)
    message: str | None = None


class MarkdownReviewDiff(BaseModel):
    model_config = ConfigDict(frozen=True)

    changes: tuple[MarkdownReviewChange, ...] = ()

    @property
    def content_changes(self) -> tuple[MarkdownReviewChange, ...]:
        return tuple(
            change
            for change in self.changes
            if change.kind is MarkdownReviewChangeKind.CONTENT_MODIFIED
        )
