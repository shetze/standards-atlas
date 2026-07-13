"""Source provenance models for protected engineering content."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CoordinateOrigin(StrEnum):
    """Origin used for bounding-box coordinates."""

    TOP_LEFT = "top_left"
    BOTTOM_LEFT = "bottom_left"


class BoundingBox(BaseModel):
    """Rectangular source location in document coordinates."""

    model_config = ConfigDict(frozen=True)

    left: float
    top: float
    right: float
    bottom: float
    coordinate_origin: CoordinateOrigin = CoordinateOrigin.TOP_LEFT

    @model_validator(mode="after")
    def validate_dimensions(self) -> BoundingBox:
        """Reject inverted rectangles while allowing arbitrary coordinates."""
        if self.right < self.left:
            raise ValueError("bounding box right must be greater than or equal to left")
        if self.bottom < self.top:
            raise ValueError("bounding box bottom must be greater than or equal to top")
        return self


class SourceEvidence(BaseModel):
    """Adapter-neutral reference to the origin of extracted content."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    locator: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    bounding_box: BoundingBox | None = None
    extraction_method: str | None = None
