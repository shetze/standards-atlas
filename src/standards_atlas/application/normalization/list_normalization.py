"""Deterministic list reconstruction and normalization operations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from standards_atlas.application.model.normalized_document import (
    NormalizationOptions,
    NormalizedItem,
    NormalizedList,
    NormalizedListItem,
    NormalizedText,
    TransformationEvent,
)

LIST_MARKER = re.compile(r"^\s*((?:\d+|[A-Za-z]|[ivxlcdmIVXLCDM]+)[.)]|[-–—•])\s+(.+)$")
_CLAUSE_REFERENCE = re.compile(r"^(?:\d+(?:\.\d+)+|[A-Z]{1,3}(?:\.\d+)*)$")
_CLAUSE_REFERENCE_START = re.compile(r"^(?:\d+(?:\.\d+)+|[A-Z]{1,3}(?:\.\d+)*)(?:\s+|$)")


class TransformationEventFactory(Protocol):
    def __call__(
        self,
        *,
        stage: str,
        rule_id: str,
        action: str,
        source_item_ids: tuple[str, ...],
        rationale: str,
        output_item_ids: tuple[str, ...] = (),
        details: dict[str, object] | None = None,
    ) -> TransformationEvent: ...


def normalize_lists(
    items: list[NormalizedItem],
    options: NormalizationOptions,
    event_factory: TransformationEventFactory,
) -> tuple[list[NormalizedItem], int, list[TransformationEvent]]:
    """Merge adjacent lists and detect consecutive marked text items."""
    if not options.normalize_lists:
        return items, 0, []
    output: list[NormalizedItem] = []
    index = 0
    normalized = 0
    events: list[TransformationEvent] = []
    while index < len(items):
        if isinstance(items[index], NormalizedList):
            lists = [items[index]]
            index += 1
            while index < len(items) and isinstance(items[index], NormalizedList):
                lists.append(items[index])
                index += 1
            if len(lists) > 1:
                merged_list = merge_lists(lists)
                output.append(merged_list)
                events.append(
                    event_factory(
                        stage="list_normalization",
                        rule_id="normalize.list.merge-adjacent",
                        action="merge",
                        source_item_ids=merged_list.source_item_ids,
                        output_item_ids=(merged_list.id,),
                        rationale="Adjacent list fragments belong to one logical list.",
                        details={"input_lists": len(lists)},
                    )
                )
                normalized += 1
            else:
                output.append(lists[0])
            continue
        run: list[tuple[NormalizedText, re.Match[str]]] = []
        cursor = index
        while cursor < len(items) and isinstance(items[cursor], NormalizedText):
            match = LIST_MARKER.match(items[cursor].text)
            if not match:
                break
            run.append((items[cursor], match))
            cursor += 1
        if len(run) >= 2:
            markers = [match.group(1) for _, match in run]
            ordered = all(marker[0].isalnum() for marker in markers)
            first = run[0][0]
            normalized_list = NormalizedList(
                id=f"normalized-list:{first.id}",
                sequence_number=first.sequence_number,
                source_item_ids=tuple(
                    source_id for item, _ in run for source_id in item.source_item_ids
                ),
                source_evidence=tuple(
                    evidence for item, _ in run for evidence in item.source_evidence
                ),
                original_labels=tuple(label for item, _ in run for label in item.original_labels),
                layout_evidence=tuple(layout for item, _ in run for layout in item.layout_evidence),
                ordered=ordered,
                items=reconstruct_list_hierarchy(
                    tuple(
                        NormalizedListItem(
                            text=match.group(2),
                            marker=match.group(1),
                            ordered=marker_is_ordered(match.group(1)),
                            source_item_ids=item.source_item_ids,
                            source_evidence=item.source_evidence,
                            layout_evidence=item.layout_evidence,
                        )
                        for item, match in run
                    )
                ),
            )
            output.append(normalized_list)
            events.append(
                event_factory(
                    stage="list_normalization",
                    rule_id="normalize.list.detect-marked-run",
                    action="create",
                    source_item_ids=normalized_list.source_item_ids,
                    output_item_ids=(normalized_list.id,),
                    rationale="Consecutive marked text items form one logical list.",
                    details={"items": len(run)},
                )
            )
            normalized += 1
            index = cursor
            continue
        output.append(items[index])
        index += 1
    return output, normalized, events


def normalize_list_marker(value: str | None) -> str | None:
    if value is None:
        return None
    marker = "".join(value.split()).rstrip(".)")
    return marker or None


def looks_like_clause_reference(text: str) -> bool:
    """Return whether text consists of a normalized clause reference."""
    return bool(_CLAUSE_REFERENCE.fullmatch("".join(text.split())))


def clause_reference_from_list_item(
    marker: str | None,
    text: str,
) -> tuple[str | None, bool]:
    if marker is not None and _CLAUSE_REFERENCE.fullmatch(marker):
        return marker, False
    match = _CLAUSE_REFERENCE_START.match(text)
    if match is None:
        return None, False
    return match.group(0).strip(), True


def marker_is_ordered(marker: str | None) -> bool:
    normalized = normalize_list_marker(marker)
    return bool(normalized and normalized[0].isalnum())


@dataclass
class _MutableListItem:
    item: NormalizedListItem
    children: list[_MutableListItem]


def reconstruct_list_hierarchy(
    items: tuple[NormalizedListItem, ...],
) -> tuple[NormalizedListItem, ...]:
    """Reconstruct nesting from stable indentation while preserving source order."""
    if len(items) < 2:
        return items
    left_positions = [_list_item_left(item) for item in items]
    known_positions = sorted({position for position in left_positions if position is not None})
    levels: list[float] = []
    for position in known_positions:
        if not levels or position - levels[-1] >= 6.0:
            levels.append(position)
    if len(levels) < 2:
        return tuple(item.model_copy(update={"depth": 0}) for item in items)

    roots: list[_MutableListItem] = []
    stack: list[_MutableListItem] = []
    for item, position in zip(items, left_positions, strict=True):
        inferred_depth = _indentation_depth(position, levels)
        depth = min(inferred_depth, len(stack))
        while len(stack) > depth:
            stack.pop()
        node = _MutableListItem(item=item.model_copy(update={"depth": depth}), children=[])
        if depth > 0 and stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
            depth = 0
            node.item = node.item.model_copy(update={"depth": 0})
        if len(stack) == depth:
            stack.append(node)
        else:
            stack[depth] = node
    return tuple(_freeze_list_item(node) for node in roots)


def merge_lists(lists: list[NormalizedList]) -> NormalizedList:
    first = lists[0]
    return NormalizedList(
        id="+".join(item.id for item in lists),
        sequence_number=first.sequence_number,
        source_item_ids=tuple(source_id for item in lists for source_id in item.source_item_ids),
        source_evidence=tuple(evidence for item in lists for evidence in item.source_evidence),
        original_labels=tuple(label for item in lists for label in item.original_labels),
        layout_evidence=tuple(layout for item in lists for layout in item.layout_evidence),
        ordered=all(item.ordered for item in lists),
        items=tuple(list_item for item in lists for list_item in item.items),
    )


def _list_item_left(item: NormalizedListItem) -> float | None:
    for evidence in item.source_evidence:
        if evidence.bounding_box is not None:
            return evidence.bounding_box.left
    return None


def _indentation_depth(position: float | None, levels: list[float]) -> int:
    if position is None:
        return 0
    return min(range(len(levels)), key=lambda index: abs(levels[index] - position))


def _freeze_list_item(node: _MutableListItem) -> NormalizedListItem:
    return node.item.model_copy(
        update={"children": tuple(_freeze_list_item(child) for child in node.children)}
    )
