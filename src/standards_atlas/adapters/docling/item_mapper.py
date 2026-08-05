"""Map native Docling items to adapter-neutral extraction models."""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Any

from standards_atlas.adapters.docling.evidence import (
    layout_evidence,
    reference_values,
    source_evidence,
)
from standards_atlas.application.model import (
    ExtractedCode,
    ExtractedFormula,
    ExtractedHeading,
    ExtractedItem,
    ExtractedList,
    ExtractedListItem,
    ExtractedPicture,
    ExtractedTable,
    ExtractedText,
    ExtractedUnknown,
    VisualAsset,
)
from standards_atlas.domain.model import SourceEvidence, TableCell, TableRow

_HEADING_LABELS = {"section_header", "title", "subtitle"}
_TEXT_LABELS = {"text", "paragraph", "caption", "footnote", "page_header", "page_footer"}
_FORMULA_LABELS = {"formula", "equation"}
_LIST_LABELS = {"list_item"}
_CLAUSE_MARKER = re.compile(r"(?:\d+(?:\.\d+)+|[A-Z]+(?:\.\d+)+)\.?$")


def referenced_caption_ids(indexed: dict[str, dict[str, Any]]) -> set[str]:
    """Return caption items owned by tables or pictures.

    Owned captions are represented on their parent visual item and must not also
    enter the body sequence as independent prose.
    """
    result: set[str] = set()
    for raw in indexed.values():
        if raw.get("label") not in {"table", "picture"}:
            continue
        result.update(reference_values(raw.get("captions")))
    return result


def _visual_asset(raw: dict[str, Any]) -> VisualAsset | None:
    image = raw.get("image")
    if not isinstance(image, dict):
        return None
    uri = _string_or_none(image.get("uri"))
    media_type = _string_or_none(image.get("mimetype"))
    if uri is None or media_type is None:
        return None
    payload = uri.encode("utf-8")
    if uri.startswith("data:") and ";base64," in uri:
        try:
            payload = base64.b64decode(uri.split(",", 1)[1], validate=True)
        except ValueError:
            payload = uri.encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    size = image.get("size") if isinstance(image.get("size"), dict) else {}
    return VisualAsset(
        media_type=media_type,
        content_hash=digest,
        data_uri=uri,
        width=_number(size.get("width")),
        height=_number(size.get("height")),
    )


def map_items(
    items: list[dict[str, Any]],
    *,
    source_id: str,
    indexed: dict[str, dict[str, Any]],
    pages: Any,
) -> list[ExtractedItem]:
    result: list[ExtractedItem] = []
    pending_list: list[tuple[dict[str, Any], SourceEvidence, int]] = []

    def flush_list() -> None:
        if not pending_list:
            return
        first_item, _, first_sequence = pending_list[0]
        all_evidence = tuple(evidence for _, evidence, _ in pending_list)
        mapped_items = tuple(
            ExtractedListItem(
                id=_item_id(item, source_sequence),
                sequence_number=source_sequence,
                text=_text(item),
                marker=_string_or_none(item.get("marker")),
                source_evidence=(evidence,),
                layout_evidence=(layout_evidence(item, pages),),
            )
            for item, evidence, source_sequence in pending_list
        )
        result.append(
            ExtractedList(
                id=_item_id(first_item, first_sequence),
                sequence_number=first_sequence,
                ordered=bool(first_item.get("enumerated")),
                items=mapped_items,
                source_evidence=all_evidence,
                original_label="list_item",
                layout_evidence=tuple(layout_evidence(item, pages) for item, _, _ in pending_list),
            )
        )
        pending_list.clear()

    for source_sequence, raw in enumerate(items):
        evidence = source_evidence(raw, source_id)
        label = str(raw.get("label", "unknown")).lower()
        if label in _LIST_LABELS:
            marker = _string_or_none(raw.get("marker"))
            if _is_clause_marker(marker):
                flush_list()
                text = _text(raw)
                clause_text = marker if not text else f"{marker} {text}"
                result.append(
                    ExtractedText(
                        id=_item_id(raw, source_sequence),
                        sequence_number=source_sequence,
                        source_evidence=(evidence,),
                        original_label=label,
                        text=clause_text,
                    )
                )
            else:
                pending_list.append((raw, evidence, source_sequence))
            continue
        flush_list()

        common = {
            "id": _item_id(raw, source_sequence),
            "sequence_number": source_sequence,
            "source_evidence": (evidence,),
            "original_label": label,
            "layout_evidence": (layout_evidence(raw, pages),),
        }
        if label == "code":
            result.append(ExtractedCode(**common, code=_text(raw)))
        elif label in _HEADING_LABELS:
            level = raw.get("level")
            result.append(
                ExtractedHeading(
                    **common,
                    text=_text(raw),
                    observed_level=level if isinstance(level, int) and level > 0 else None,
                )
            )
        elif label in _FORMULA_LABELS:
            semantic_text = _string_or_none(raw.get("text"))
            original_expression = _string_or_none(raw.get("orig"))
            result.append(
                ExtractedFormula(
                    **common,
                    expression=semantic_text or original_expression or "",
                    original_expression=original_expression,
                    extraction_status=(
                        "machine_extracted" if semantic_text is not None else "visual_only"
                    ),
                )
            )
        elif label == "table" or "data" in raw and isinstance(raw.get("data"), dict):
            result.append(
                ExtractedTable(
                    **common,
                    rows=_table_rows(raw),
                    caption=_caption(raw, indexed),
                )
            )
        elif label == "picture":
            result.append(
                ExtractedPicture(
                    **common,
                    caption=_caption(raw, indexed),
                    description=_string_or_none(raw.get("text")),
                    image_reference=_string_or_none(raw.get("self_ref")),
                    visual_asset=_visual_asset(raw),
                )
            )
        elif label in _TEXT_LABELS:
            result.append(ExtractedText(**common, text=_text(raw)))
        else:
            result.append(
                ExtractedUnknown(
                    **common,
                    text=_string_or_none(raw.get("text")),
                    raw_attributes=_diagnostic_attributes(raw),
                )
            )
    flush_list()
    return _resequence_items(result)


def _is_clause_marker(marker: str | None) -> bool:
    if marker is None:
        return False
    normalized = "".join(marker.split()).rstrip(".)")
    return bool(_CLAUSE_MARKER.fullmatch(normalized))


def _resequence_items(items: list[ExtractedItem]) -> list[ExtractedItem]:
    return [
        item.model_copy(update={"sequence_number": sequence_number})
        for sequence_number, item in enumerate(items)
    ]


def _diagnostic_attributes(raw: dict[str, Any]) -> dict[str, Any]:
    retained = {}
    for key in ("label", "self_ref", "level", "marker", "enumerated"):
        value = raw.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            retained[key] = value
    return retained


def _table_rows(raw: dict[str, Any]) -> tuple[TableRow, ...]:
    data = raw.get("data")
    if not isinstance(data, dict):
        return ()
    cells = data.get("table_cells")
    if not isinstance(cells, list):
        return ()
    rows: dict[int, list[tuple[int, TableCell]]] = {}
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        row_index = cell.get("start_row_offset_idx", cell.get("row_idx", 0))
        column_index = cell.get("start_col_offset_idx", cell.get("col_idx", 0))
        if not isinstance(row_index, int) or not isinstance(column_index, int):
            continue
        row_span = cell.get("row_span", 1)
        column_span = cell.get("col_span", 1)
        mapped = TableCell(
            text=str(cell.get("text", "")),
            row_span=row_span if isinstance(row_span, int) and row_span > 0 else 1,
            column_span=column_span if isinstance(column_span, int) and column_span > 0 else 1,
            is_header=bool(cell.get("column_header") or cell.get("row_header")),
        )
        rows.setdefault(row_index, []).append((column_index, mapped))
    return tuple(
        TableRow(cells=tuple(cell for _, cell in sorted(row_cells)))
        for _, row_cells in sorted(rows.items())
    )


def _caption(raw: dict[str, Any], indexed: dict[str, dict[str, Any]]) -> str | None:
    for reference in reference_values(raw.get("captions")):
        caption = indexed.get(reference)
        if caption is not None:
            text = _string_or_none(caption.get("text"))
            if text is not None:
                return text
    captions = raw.get("captions")
    if isinstance(captions, list):
        for caption in captions:
            if isinstance(caption, dict) and isinstance(caption.get("text"), str):
                return caption["text"]
    return None


def _text(raw: dict[str, Any]) -> str:
    return str(raw.get("text", raw.get("orig", "")))


def _item_id(raw: dict[str, Any], fallback: int) -> str:
    reference = raw.get("self_ref")
    return reference if isinstance(reference, str) and reference else f"docling-item-{fallback}"


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
