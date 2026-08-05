"""Conservative reading-order repairs for native Docling items."""

from __future__ import annotations

import re
from typing import Any

_HEADING_LABELS = {"section_header", "title", "subtitle"}
_ANNEX_HEADING = re.compile(r"^\s*Annex\s+([A-Z]+)\s*$", re.IGNORECASE)
_CLAUSE_HEADING = re.compile(r"^\s*((?:\d+|[A-Z]+)(?:\.\d+)+)\b")


def repair_reading_order(body_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply all conservative body-order repairs in a stable sequence."""
    repaired = repair_misordered_annex_headings(body_items)
    return repair_misordered_clause_headings(repaired)


def repair_misordered_annex_headings(
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


def repair_misordered_clause_headings(
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


def merge_orphaned_items(
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


def _text(raw: dict[str, Any]) -> str:
    return str(raw.get("text", raw.get("orig", "")))


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
