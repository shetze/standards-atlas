"""Read native Docling JSON into adapter-neutral extraction models."""

from __future__ import annotations

import base64
import hashlib
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
    LayoutEvidence,
    VisualAsset,
)
from standards_atlas.domain.model import (
    ArtifactLineage,
    BoundingBox,
    CoordinateOrigin,
    SourceEvidence,
    TableCell,
    TableRow,
    artifact_reference,
)

_HEADING_LABELS = {"section_header", "title", "subtitle"}
_TEXT_LABELS = {"text", "paragraph", "caption", "footnote", "page_header", "page_footer"}
_FORMULA_LABELS = {"formula", "equation"}
_LIST_LABELS = {"list_item"}
_CLAUSE_MARKER = re.compile(r"(?:\d+(?:\.\d+)+|[A-Z]+(?:\.\d+)+)\.?$")
_ANNEX_HEADING = re.compile(r"^\s*Annex\s+([A-Z]+)\s*$", re.IGNORECASE)
_CLAUSE_HEADING = re.compile(r"^\s*((?:\d+|[A-Z]+)(?:\.\d+)+)\b")


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
        caption_references = _referenced_caption_ids(indexed)
        ordered = [
            item
            for item in _ordered_items(payload, indexed)
            if item.get("self_ref") not in caption_references
        ]
        items = _map_items(
            ordered,
            source_id=source_id,
            indexed=indexed,
            pages=payload.get("pages"),
        )
        origin = payload.get("origin") if isinstance(payload.get("origin"), dict) else {}

        metadata = ExtractionMetadata(
            converter="docling",
            source_path=_string_or_none(origin.get("filename")),
        )
        draft = ExtractedDocument(
            source_id=source_id,
            items=tuple(items),
            metadata=metadata,
        )
        source_artifact = artifact_reference(
            "source_document",
            {"source_id": source_id, "source_path": metadata.source_path},
            location=metadata.source_path,
        )
        extraction_artifact = artifact_reference(
            "docling_extraction",
            draft,
            location=str(source),
            media_type="application/json",
        )
        return draft.model_copy(
            update={
                "lineage": ArtifactLineage(
                    artifact=extraction_artifact,
                    derived_from=(source_artifact,),
                )
            }
        )


def _referenced_caption_ids(indexed: dict[str, dict[str, Any]]) -> set[str]:
    """Return caption items owned by tables or pictures.

    Owned captions are represented on their parent visual item and must not also
    enter the body sequence as independent prose.
    """
    result: set[str] = set()
    for raw in indexed.values():
        if raw.get("label") not in {"table", "picture"}:
            continue
        result.update(_reference_values(raw.get("captions")))
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

    def visit(node: Any, group_path: tuple[str, ...] = ()) -> Iterable[dict[str, Any]]:
        if not isinstance(node, dict):
            return

        reference = node.get("$ref")
        if isinstance(reference, str) and reference in indexed:
            resolved = indexed[reference]
            if _is_group(reference, resolved):
                if reference in visited_groups:
                    return
                visited_groups.add(reference)
                yield from visit(resolved, (*group_path, reference))
                return
            if reference in yielded_items:
                return
            yielded_items.add(reference)
            enriched = dict(resolved)
            enriched["_atlas_group_path"] = group_path
            yield enriched
            return

        children = node.get("children", []) if isinstance(node.get("children"), list) else []
        for child in children:
            yield from visit(child, group_path)

    body_items = list(visit(body)) if isinstance(body, dict) else []
    body_items = _repair_misordered_annex_headings(body_items)
    body_items = _repair_misordered_clause_headings(body_items)

    # Some Docling documents contain content items which are not reachable from
    # the body tree. They still belong to the document, but appending them at the
    # end corrupts reading order when Docling omitted a heading from the body
    # tree. Reinsert only these orphaned items from their page geometry while
    # preserving the declared order of all body-reachable items.
    orphaned_items = [
        _with_group_path(item, indexed)
        for reference, item in indexed.items()
        if not _is_group(reference, item) and reference not in yielded_items
    ]
    yield from _merge_orphaned_items(body_items, orphaned_items)


def _repair_misordered_annex_headings(
    body_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Move a misplaced Annex heading block before its first child clause.

    Docling occasionally emits a complete but locally wrong body order: the
    first clauses of an annex appear before the annex heading, even though the
    page geometry unambiguously places the heading above them.  Repair only
    this narrow case.  All unrelated body items retain their declared order.
    """
    result = list(body_items)
    index = 0
    while index < len(result):
        annex = _annex_reference(result[index])
        annex_key = _layout_key(result[index])
        if annex is None or annex_key is None:
            index += 1
            continue

        child_index = _first_preceding_annex_child_index(
            result,
            before=index,
            annex=annex,
            page=annex_key[0],
        )
        if child_index is None:
            index += 1
            continue

        child_key = _layout_key(result[child_index])
        if child_key is None or not annex_key < child_key:
            index += 1
            continue

        block_end = index + 1
        while block_end < len(result):
            item_key = _layout_key(result[block_end])
            if item_key is None or item_key[0] != annex_key[0] or not item_key < child_key:
                break
            block_end += 1

        heading_block = result[index:block_end]
        del result[index:block_end]
        result[child_index:child_index] = heading_block

        # Continue after the repaired block.  Restarting from there also keeps
        # the algorithm safe when several annexes occur in one document.
        index = child_index + len(heading_block)
    return result


def _repair_misordered_clause_headings(
    body_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Repair a locally misplaced numbered clause heading from page geometry.

    Docling can emit a heading after content that is visually below it.  Only
    repair an item when all of the following are true:

    * it is a heading with a parseable numeric/annex clause reference;
    * its reference is earlier than a preceding heading on the same page; and
    * its bounding box is geometrically above that preceding heading.

    The heading is then inserted at its geometric position on that page.  No
    non-heading item is reordered, which keeps tables, lists, formulas and
    multi-column body content in their declared order.
    """
    result = list(body_items)
    index = 0
    while index < len(result):
        candidate_reference = _clause_reference_key(result[index])
        candidate_layout = _layout_key(result[index])
        if candidate_reference is None or candidate_layout is None:
            index += 1
            continue

        preceding_heading_indexes = [
            preceding_index
            for preceding_index in range(index)
            if _clause_reference_key(result[preceding_index]) is not None
            and (_layout_key(result[preceding_index]) or (-1, 0.0, 0.0))[0] == candidate_layout[0]
        ]
        if not preceding_heading_indexes:
            index += 1
            continue

        preceding_index = preceding_heading_indexes[-1]
        preceding_reference = _clause_reference_key(result[preceding_index])
        preceding_layout = _layout_key(result[preceding_index])
        if (
            preceding_reference is None
            or preceding_layout is None
            or candidate_reference >= preceding_reference
            or candidate_layout >= preceding_layout
        ):
            index += 1
            continue

        insertion_index = index
        for possible_index, item in enumerate(result[:index]):
            item_layout = _layout_key(item)
            if (
                item_layout is not None
                and item_layout[0] == candidate_layout[0]
                and item_layout > candidate_layout
            ):
                insertion_index = possible_index
                break

        if insertion_index == index:
            index += 1
            continue

        candidate = result.pop(index)
        result.insert(insertion_index, candidate)
        index = insertion_index + 1

    return result


def _clause_reference_key(item: dict[str, Any]) -> tuple[tuple[int, int | str], ...] | None:
    label = str(item.get("label", "")).lower()
    if label not in _HEADING_LABELS:
        return None
    match = _CLAUSE_HEADING.match(_text(item))
    if not match:
        return None
    parts: list[tuple[int, int | str]] = []
    for token in match.group(1).split("."):
        if token.isdigit():
            parts.append((0, int(token)))
        else:
            parts.append((1, token.upper()))
    return tuple(parts)


def _annex_reference(item: dict[str, Any]) -> str | None:
    label = str(item.get("label", "")).lower()
    if label not in _HEADING_LABELS:
        return None
    match = _ANNEX_HEADING.fullmatch(_text(item))
    return match.group(1).upper() if match else None


def _first_preceding_annex_child_index(
    items: list[dict[str, Any]],
    *,
    before: int,
    annex: str,
    page: int,
) -> int | None:
    child_pattern = re.compile(rf"^\s*{re.escape(annex)}\.\d+(?:\.\d+)*\b")
    for index, item in enumerate(items[:before]):
        key = _layout_key(item)
        if key is None or key[0] != page:
            continue
        if child_pattern.match(_text(item)):
            return index
    return None


def _merge_orphaned_items(
    body_items: list[dict[str, Any]],
    orphaned_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reinsert body-orphaned items without reordering declared body content."""
    result = list(body_items)
    ordered_orphans = sorted(
        enumerate(orphaned_items),
        key=lambda entry: (_layout_key(entry[1]) is None, _layout_key(entry[1]), entry[0]),
    )
    for _, orphan in ordered_orphans:
        orphan_key = _layout_key(orphan)
        if orphan_key is None:
            result.append(orphan)
            continue
        insertion_index = len(result)
        for index, item in enumerate(result):
            item_key = _layout_key(item)
            if item_key is not None and item_key > orphan_key:
                insertion_index = index
                break
        result.insert(insertion_index, orphan)
    return result


def _layout_key(item: dict[str, Any]) -> tuple[int, float, float] | None:
    provenance = item.get("prov")
    first = provenance[0] if isinstance(provenance, list) and provenance else None
    if not isinstance(first, dict):
        return None
    page = first.get("page_no")
    bbox = first.get("bbox")
    if not isinstance(page, int) or page < 1 or not isinstance(bbox, dict):
        return None
    left = _number(bbox.get("l", bbox.get("left")))
    top = _number(bbox.get("t", bbox.get("top")))
    bottom = _number(bbox.get("b", bbox.get("bottom")))
    if left is None or top is None or bottom is None:
        return None
    origin = str(bbox.get("coord_origin", bbox.get("coordinate_origin", "top_left"))).lower()
    vertical = -max(top, bottom) if "bottom" in origin else min(top, bottom)
    return page, vertical, left


def _is_group(reference: str, item: dict[str, Any]) -> bool:
    if reference.startswith("#/groups/"):
        return True
    label = str(item.get("label", "")).lower()
    return label in {"group", "list", "ordered_list", "unordered_list", "chapter"}


def _map_items(
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
                layout_evidence=(_layout_evidence(item, pages),),
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
                layout_evidence=tuple(_layout_evidence(item, pages) for item, _, _ in pending_list),
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
            "layout_evidence": (_layout_evidence(raw, pages),),
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


def _with_group_path(raw: dict[str, Any], indexed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    enriched = dict(raw)
    path: list[str] = []
    seen: set[str] = set()
    parent_reference = _single_reference(raw.get("parent"))
    while parent_reference and parent_reference not in seen:
        seen.add(parent_reference)
        parent = indexed.get(parent_reference)
        if parent is None or not _is_group(parent_reference, parent):
            break
        path.append(parent_reference)
        parent_reference = _single_reference(parent.get("parent"))
    enriched["_atlas_group_path"] = tuple(reversed(path))
    return enriched


def _layout_evidence(raw: dict[str, Any], pages: Any) -> LayoutEvidence:
    page_number = None
    provenance = raw.get("prov")
    if isinstance(provenance, list) and provenance and isinstance(provenance[0], dict):
        candidate = provenance[0].get("page_no")
        if isinstance(candidate, int) and candidate >= 1:
            page_number = candidate
    page_width, page_height = _page_dimensions(pages, page_number)
    return LayoutEvidence(
        source_reference=_string_or_none(raw.get("self_ref")),
        content_layer=_string_or_none(raw.get("content_layer")),
        parent_reference=_single_reference(raw.get("parent")),
        group_path=tuple(raw.get("_atlas_group_path", ())),
        page_width=page_width,
        page_height=page_height,
        original_marker=_string_or_none(raw.get("marker")),
        original_text=_string_or_none(raw.get("orig")) or _string_or_none(raw.get("text")),
        caption_references=_reference_values(raw.get("captions")),
        reference_references=_reference_values(raw.get("references")),
        footnote_references=_reference_values(raw.get("footnotes")),
    )


def _page_dimensions(pages: Any, page_number: int | None) -> tuple[float | None, float | None]:
    if page_number is None or not isinstance(pages, dict):
        return None, None
    page = pages.get(str(page_number), pages.get(page_number))
    size = page.get("size") if isinstance(page, dict) else None
    if not isinstance(size, dict):
        return None, None
    return _number(size.get("width")), _number(size.get("height"))


def _single_reference(value: Any) -> str | None:
    values = _reference_values(value)
    return values[0] if values else None


def _reference_values(value: Any) -> tuple[str, ...]:
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


def _caption(raw: dict[str, Any], indexed: dict[str, dict[str, Any]]) -> str | None:
    for reference in _reference_values(raw.get("captions")):
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
