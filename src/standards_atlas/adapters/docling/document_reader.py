"""Read native Docling JSON into adapter-neutral extraction models."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from standards_atlas.adapters.docling.errors import DoclingDocumentValidationError
from standards_atlas.application.model import (
    ExtractedCode,
    ExtractedDocument,
    ExtractedFormula,
    ExtractedHeading,
    ExtractedItem,
    ExtractedList,
    ExtractedListItem,
    ExtractedPicture,
    ExtractedTable,
    ExtractedText,
    ExtractedUnknown,
    ExtractionMetadata,
)
from standards_atlas.domain.model import (
    BoundingBox,
    CoordinateOrigin,
    SourceEvidence,
    TableCell,
    TableRow,
)

_HEADING_LABELS = {"section_header", "title", "subtitle"}
_TEXT_LABELS = {"text", "paragraph", "caption", "footnote", "page_header", "page_footer"}
_FORMULA_LABELS = {"formula", "equation"}
_LIST_LABELS = {"list_item"}
_CLAUSE_MARKER = re.compile(r"(?:\d+(?:\.\d+)+|[A-Z]+(?:\.\d+)+)\.?$")


class DoclingJsonReader:
    """Interpret persisted native Docling JSON without importing Docling itself."""

    def read(self, source: Path) -> ExtractedDocument:
        """Read a native Docling document in its declared reading order."""
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            message = f"Cannot read Docling JSON {source}: {exc}"
            raise DoclingDocumentValidationError(message) from exc
        if not isinstance(payload, dict):
            raise DoclingDocumentValidationError("Docling JSON must contain an object")

        source_id = _source_id(payload, source)
        indexed = _index_items(payload)
        ordered = list(_ordered_items(payload, indexed))
        items = _map_items(ordered, source_id=source_id)
        origin = payload.get("origin") if isinstance(payload.get("origin"), dict) else {}

        return ExtractedDocument(
            source_id=source_id,
            items=tuple(items),
            metadata=ExtractionMetadata(
                converter="docling",
                source_path=_string_or_none(origin.get("filename")),
            ),
        )


def _source_id(payload: dict[str, Any], source: Path) -> str:
    name = payload.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    origin = payload.get("origin")
    if isinstance(origin, dict):
        filename = origin.get("filename")
        if isinstance(filename, str) and filename.strip():
            return Path(filename).stem
    return source.stem


def _index_items(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for collection_name in (
        "texts",
        "tables",
        "pictures",
        "key_value_items",
        "form_items",
        "groups",
    ):
        collection = payload.get(collection_name, [])
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            reference = item.get("self_ref")
            if isinstance(reference, str):
                result[reference] = item
    return result


def _ordered_items(
    payload: dict[str, Any],
    indexed: dict[str, dict[str, Any]],
) -> Iterable[dict[str, Any]]:
    body = payload.get("body")
    yielded_items: set[str] = set()
    visited_groups: set[str] = set()

    def visit(node: Any) -> Iterable[dict[str, Any]]:
        if not isinstance(node, dict):
            return

        reference = node.get("$ref")
        if isinstance(reference, str) and reference in indexed:
            resolved = indexed[reference]
            if _is_group(reference, resolved):
                if reference in visited_groups:
                    return
                visited_groups.add(reference)
                yield from visit(resolved)
                return
            if reference in yielded_items:
                return
            yielded_items.add(reference)
            yield resolved
            return

        children = node.get("children", []) if isinstance(node.get("children"), list) else []
        for child in children:
            yield from visit(child)

    if isinstance(body, dict):
        yield from visit(body)

    # Some Docling documents contain content items which are not reachable from
    # the body tree. Keep them, but append only real content items; group nodes
    # are traversal helpers and must never become extracted document items.
    for reference, item in indexed.items():
        if _is_group(reference, item) or reference in yielded_items:
            continue
        yielded_items.add(reference)
        yield item


def _is_group(reference: str, item: dict[str, Any]) -> bool:
    if reference.startswith("#/groups/"):
        return True
    label = str(item.get("label", "")).lower()
    return label in {"group", "list", "ordered_list", "unordered_list", "chapter"}


def _map_items(items: list[dict[str, Any]], *, source_id: str) -> list[ExtractedItem]:
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
            )
        )
        pending_list.clear()

    for source_sequence, raw in enumerate(items):
        evidence = _source_evidence(raw, source_id)
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
            result.append(ExtractedFormula(**common, expression=_text(raw)))
        elif label == "table" or "data" in raw and isinstance(raw.get("data"), dict):
            result.append(ExtractedTable(**common, rows=_table_rows(raw), caption=_caption(raw)))
        elif label == "picture":
            result.append(
                ExtractedPicture(
                    **common,
                    caption=_caption(raw),
                    description=_string_or_none(raw.get("text")),
                    image_reference=_string_or_none(raw.get("self_ref")),
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


def _source_evidence(raw: dict[str, Any], source_id: str) -> SourceEvidence:
    provenance = raw.get("prov")
    first = provenance[0] if isinstance(provenance, list) and provenance else {}
    if not isinstance(first, dict):
        first = {}
    bbox_data = first.get("bbox")
    bbox = _bounding_box(bbox_data) if isinstance(bbox_data, dict) else None
    page = first.get("page_no")
    return SourceEvidence(
        source_id=source_id,
        source_type="pdf",
        locator=_string_or_none(raw.get("self_ref")),
        page_number=page if isinstance(page, int) and page >= 1 else None,
        bounding_box=bbox,
        extraction_method="docling",
    )


def _bounding_box(data: dict[str, Any]) -> BoundingBox | None:
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


def _caption(raw: dict[str, Any]) -> str | None:
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
