"""Source provenance models for protected engineering content."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTEXT_SOURCE_PACKAGE_SCHEMA_VERSION = 1
CONTEXT_SOURCE_PACKAGE_CONTRACT = "source-bound-context-input-v1"
CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT = "source-bound-context-binding-v1"


class ContextInputFingerprints(BaseModel):
    """Text-free fingerprints of the source/input dimensions bound to one proposal input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_state_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    candidate_space_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    selection_decision_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    actual_input_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ContextSourcePackageBinding(BaseModel):
    """Text-free immutable identity of a privately persisted source/input package."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: Literal["source-bound-context-binding-v1"] = (
        CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT
    )
    package_schema_version: Literal[1] = CONTEXT_SOURCE_PACKAGE_SCHEMA_VERSION
    package_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    document_key: str = Field(min_length=1)
    document_revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_clause_id: str = Field(min_length=1)
    target_reference: str = Field(min_length=1)
    selection_contract_id: str = Field(min_length=1)
    selection_profile_id: str = Field(min_length=1)
    selection_completeness: str = Field(min_length=1)
    selection_gap_codes: tuple[str, ...] = ()
    fingerprints: ContextInputFingerprints


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
