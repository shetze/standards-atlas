"""Adapter-neutral representation of observed document content."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model import ArtifactLineage, SourceEvidence, TableRow


class LayoutEvidence(BaseModel):
    """Adapter-neutral layout and structural observations from the extractor."""

    model_config = ConfigDict(frozen=True)

    source_reference: str | None = None
    content_layer: str | None = None
    parent_reference: str | None = None
    group_path: tuple[str, ...] = ()
    page_width: float | None = Field(default=None, gt=0)
    page_height: float | None = Field(default=None, gt=0)
    original_marker: str | None = None
    original_text: str | None = None
    caption_references: tuple[str, ...] = ()
    reference_references: tuple[str, ...] = ()
    footnote_references: tuple[str, ...] = ()


class ExtractedItemBase(BaseModel):
    """Common fields for content observed in an external source document."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    sequence_number: int = Field(ge=0)
    source_evidence: tuple[SourceEvidence, ...] = ()
    original_label: str | None = None
    layout_evidence: tuple[LayoutEvidence, ...] = ()


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
    """One item in an observed list with its own source identity."""

    model_config = ConfigDict(frozen=True)

    id: str | None = None
    sequence_number: int | None = Field(default=None, ge=0)
    text: str
    marker: str | None = None
    source_evidence: tuple[SourceEvidence, ...] = ()
    layout_evidence: tuple[LayoutEvidence, ...] = ()


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


class VisualAsset(BaseModel):
    """Extractor-provided visual payload with stable identity."""

    model_config = ConfigDict(frozen=True)

    media_type: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_uri: str | None = None
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)


class ExtractedPicture(ExtractedItemBase):
    """Observed figure or diagram."""

    type: Literal["picture"] = "picture"
    caption: str | None = None
    description: str | None = None
    image_reference: str | None = None
    visual_asset: VisualAsset | None = None


class ExtractedFormula(ExtractedItemBase):
    """Observed mathematical or engineering expression."""

    type: Literal["formula"] = "formula"
    expression: str
    original_expression: str | None = None
    representation: Literal["latex", "mathml", "text"] = "text"
    extraction_status: Literal["visual_only", "machine_extracted", "human_verified"] = (
        "machine_extracted"
    )
    visual_asset: VisualAsset | None = None


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
    lineage: ArtifactLineage | None = None
