"""Source and layout evidence mapping for native Docling items."""

from __future__ import annotations

from typing import Any

from standards_atlas.application.model import LayoutEvidence
from standards_atlas.domain.model import BoundingBox, CoordinateOrigin, SourceEvidence


def layout_evidence(raw: dict[str, Any], pages: Any) -> LayoutEvidence:
    page_number = None
    provenance = raw.get("prov")
    if isinstance(provenance, list) and provenance and isinstance(provenance[0], dict):
        candidate = provenance[0].get("page_no")
        if isinstance(candidate, int) and candidate >= 1:
            page_number = candidate
    page_width, page_height = page_dimensions(pages, page_number)
    return LayoutEvidence(
        source_reference=_string_or_none(raw.get("self_ref")),
        content_layer=_string_or_none(raw.get("content_layer")),
        parent_reference=single_reference(raw.get("parent")),
        group_path=tuple(raw.get("_atlas_group_path", ())),
        page_width=page_width,
        page_height=page_height,
        original_marker=_string_or_none(raw.get("marker")),
        original_text=_string_or_none(raw.get("orig")) or _string_or_none(raw.get("text")),
        caption_references=reference_values(raw.get("captions")),
        reference_references=reference_values(raw.get("references")),
        footnote_references=reference_values(raw.get("footnotes")),
    )


def page_dimensions(pages: Any, page_number: int | None) -> tuple[float | None, float | None]:
    if page_number is None or not isinstance(pages, dict):
        return None, None
    page = pages.get(str(page_number), pages.get(page_number))
    size = page.get("size") if isinstance(page, dict) else None
    if not isinstance(size, dict):
        return None, None
    return _number(size.get("width")), _number(size.get("height"))


def single_reference(value: Any) -> str | None:
    values = reference_values(value)
    return values[0] if values else None


def reference_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, dict):
        reference = value.get("$ref")
        return (reference,) if isinstance(reference, str) else ()
    if not isinstance(value, list):
        return ()
    result = []
    for entry in value:
        if isinstance(entry, dict) and isinstance(entry.get("$ref"), str):
            result.append(entry["$ref"])
    return tuple(result)


def source_evidence(raw: dict[str, Any], source_id: str) -> SourceEvidence:
    provenance = raw.get("prov")
    first = provenance[0] if isinstance(provenance, list) and provenance else {}
    if not isinstance(first, dict):
        first = {}
    bbox_data = first.get("bbox")
    bbox = bounding_box(bbox_data) if isinstance(bbox_data, dict) else None
    page = first.get("page_no")
    return SourceEvidence(
        source_id=source_id,
        source_type="pdf",
        locator=_string_or_none(raw.get("self_ref")),
        page_number=page if isinstance(page, int) and page >= 1 else None,
        bounding_box=bbox,
        extraction_method="docling",
    )


def bounding_box(data: dict[str, Any]) -> BoundingBox | None:
    left = _number(data.get("l", data.get("left")))
    top = _number(data.get("t", data.get("top")))
    right = _number(data.get("r", data.get("right")))
    bottom = _number(data.get("b", data.get("bottom")))
    if None in (left, top, right, bottom):
        return None
    origin = str(data.get("coord_origin", data.get("coordinate_origin", "top_left"))).lower()
    coordinate_origin = (
        CoordinateOrigin.BOTTOM_LEFT if "bottom" in origin else CoordinateOrigin.TOP_LEFT
    )
    return BoundingBox(
        left=min(left, right),
        top=min(top, bottom),
        right=max(left, right),
        bottom=max(top, bottom),
        coordinate_origin=coordinate_origin,
    )


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
