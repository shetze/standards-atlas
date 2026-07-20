"""Normalized, provenance-preserving representation of extracted documents."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model import SourceEvidence, TableRow


class NormalizationOptions(BaseModel):
    """Deterministic options applied during document normalization."""

    model_config = ConfigDict(frozen=True)

    unicode_form: Literal["NFC", "NFKC"] = "NFC"
    normalize_whitespace: bool = True
    suppress_headers: bool = True
    suppress_footers: bool = True
    repair_hyphenation: bool = True
    merge_text_fragments: bool = True
    normalize_lists: bool = True
    suppress_repeated_page_elements: bool = False
    fail_on_data_loss: bool = True
    repeated_page_element_min_occurrences: int = Field(default=3, ge=2)
    page_ranges: tuple[tuple[int, int | None], ...] = ()
    exclude_page_ranges: tuple[tuple[int, int | None], ...] = ()
    page_list: tuple[int, ...] = ()


class NormalizationIssue(BaseModel):
    """A diagnostic emitted for a potentially ambiguous transformation."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    item_ids: tuple[str, ...] = ()
    message: str


class SuppressedItem(BaseModel):
    """An extracted item excluded from the active normalized sequence."""

    model_config = ConfigDict(frozen=True)

    source_item_id: str
    reason: Literal["header", "footer", "page_number", "content_selection"]
    confidence: float = Field(ge=0.0, le=1.0)
    text: str | None = None
    page_number: int | None = Field(default=None, ge=1)


class NormalizedItemBase(BaseModel):
    """Common metadata of a normalized document item."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    sequence_number: int = Field(ge=0)
    source_item_ids: tuple[str, ...]
    source_evidence: tuple[SourceEvidence, ...] = ()
    original_labels: tuple[str, ...] = ()


class NormalizedText(NormalizedItemBase):
    type: Literal["text"] = "text"
    text: str


class NormalizedHeading(NormalizedItemBase):
    type: Literal["heading"] = "heading"
    text: str
    observed_level: int | None = Field(default=None, ge=1)


class NormalizedListItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    marker: str | None = None
    children: tuple[NormalizedListItem, ...] = ()
    source_item_ids: tuple[str, ...] = ()


class NormalizedList(NormalizedItemBase):
    type: Literal["list"] = "list"
    ordered: bool = False
    items: tuple[NormalizedListItem, ...]


class NormalizedTable(NormalizedItemBase):
    type: Literal["table"] = "table"
    rows: tuple[TableRow, ...]
    caption: str | None = None


class NormalizedPicture(NormalizedItemBase):
    type: Literal["picture"] = "picture"
    caption: str | None = None
    description: str | None = None
    image_reference: str | None = None


class NormalizedFormula(NormalizedItemBase):
    type: Literal["formula"] = "formula"
    expression: str
    representation: Literal["latex", "mathml", "text"] = "text"


class NormalizedCode(NormalizedItemBase):
    type: Literal["code"] = "code"
    code: str
    language: str | None = None


class NormalizedUnknown(NormalizedItemBase):
    type: Literal["unknown"] = "unknown"
    text: str | None = None
    raw_attributes: dict[str, Any] = Field(default_factory=dict)


NormalizedItem = Annotated[
    NormalizedText
    | NormalizedHeading
    | NormalizedList
    | NormalizedTable
    | NormalizedPicture
    | NormalizedFormula
    | NormalizedCode
    | NormalizedUnknown,
    Field(discriminator="type"),
]


class NormalizationStatistics(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_items: int = 0
    output_items: int = 0
    headers_suppressed: int = 0
    footers_suppressed: int = 0
    page_numbers_suppressed: int = 0
    hyphenations_repaired: int = 0
    text_fragments_merged: int = 0
    lists_normalized: int = 0
    code_blocks: int = 0
    active_source_items: int = 0
    suppressed_source_items: int = 0
    unaccounted_source_items: int = 0
    duplicate_source_items: int = 0
    source_pages: int = 0
    selected_pages: int = 0
    excluded_pages: int = 0


class NormalizationMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 2
    normalizer_version: str
    source_extraction_hash: str
    created_at: datetime
    options: NormalizationOptions
    statistics: NormalizationStatistics


class NormalizedExtractedDocument(BaseModel):
    """Normalized document ready for structural analysis and alignment."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1)
    items: tuple[NormalizedItem, ...] = ()
    suppressed_items: tuple[SuppressedItem, ...] = ()
    issues: tuple[NormalizationIssue, ...] = ()
    metadata: NormalizationMetadata
