"""Annotations attached to engineering document clauses."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model.identifiers import AnnotationId, ClauseId


class AnnotationType(StrEnum):
    """Semantic purpose of a clause annotation."""

    TITLE = "title"
    SUMMARY = "summary"
    COMMENT = "comment"
    EXPLANATION = "explanation"
    RATIONALE = "rationale"
    EXAMPLE = "example"
    WARNING = "warning"
    NOTE = "note"
    DISCUSSION = "discussion"
    LINK_COLLECTION = "link_collection"


class AnnotationVisibility(StrEnum):
    """Visibility and publication policy of an annotation."""

    PUBLIC = "public"
    LOCAL = "local"
    PRIVATE = "private"


class ClauseAnnotation(BaseModel):
    """Additional knowledge associated with one clause."""

    model_config = ConfigDict(frozen=True)

    id: AnnotationId
    clause_id: ClauseId

    annotation_type: AnnotationType
    visibility: AnnotationVisibility

    content: str = Field(min_length=1)
    title: str | None = None

    author: str | None = None
    generated_by: str | None = None
    source: str | None = None
