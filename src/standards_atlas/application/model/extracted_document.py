"""Adapter-neutral representation of observed document content."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model import SourceEvidence, TableRow


class ExtractedItemBase(BaseModel):
    """Common fields for content observed in an external source document."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    sequence_number: int = Field(ge=0)
    source_evidence: tuple[SourceEvidence, ...] = ()
    original_label: str | None = None


class ExtractedText(ExtractedItemBase):
    """Observed prose that has not yet been assigned to a clause."""

    type: Literal["text"] = "text"
    text: str


class ExtractedHeading(ExtractedItemBase):
    """Observed heading candidate."""

    type: Literal["heading"] = "heading"
    text: str
    observed_level: int | None = Field(default=None, ge=1)


class ExtractedListItem(BaseModel):
    """One item in an observed list."""

    model_config = ConfigDict(frozen=True)

    text: str
    marker: str | None = None


class ExtractedList(ExtractedItemBase):
    """Observed ordered or unordered list."""

    type: Literal["list"] = "list"
    ordered: bool = False
    items: tuple[ExtractedListItem, ...]


class ExtractedTable(ExtractedItemBase):
    """Observed table with adapter-neutral rows and cells."""

    type: Literal["table"] = "table"
    rows: tuple[TableRow, ...]
    caption: str | None = None


class ExtractedPicture(ExtractedItemBase):
    """Observed figure or diagram."""

    type: Literal["picture"] = "picture"
    caption: str | None = None
    description: str | None = None
    image_reference: str | None = None


class ExtractedFormula(ExtractedItemBase):
    """Observed mathematical or engineering expression."""

    type: Literal["formula"] = "formula"
    expression: str
    representation: Literal["latex", "mathml", "text"] = "text"


class ExtractedCode(ExtractedItemBase):
    """Observed code or preformatted text."""

    type: Literal["code"] = "code"
    code: str
    language: str | None = None


class ExtractedUnknown(ExtractedItemBase):
    """Observed Docling item without a supported semantic mapping."""

    type: Literal["unknown"] = "unknown"
    text: str | None = None
    raw_attributes: dict[str, Any] = Field(default_factory=dict)


ExtractedItem = Annotated[
    ExtractedText
    | ExtractedHeading
    | ExtractedList
    | ExtractedTable
    | ExtractedPicture
    | ExtractedFormula
    | ExtractedCode
    | ExtractedUnknown,
    Field(discriminator="type"),
]


class ExtractionMetadata(BaseModel):
    """Metadata needed to reproduce and diagnose an extraction."""

    model_config = ConfigDict(frozen=True)

    converter: str
    converter_version: str | None = None
    source_sha256: str | None = None
    source_path: str | None = None


class ExtractedDocument(BaseModel):
    """Ordered content observed by an extraction adapter."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1)
    items: tuple[ExtractedItem, ...] = ()
    metadata: ExtractionMetadata
