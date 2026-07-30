"""Deterministic extraction of method and technique candidates."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from standards_atlas.application.model.normalized_document import (
    MethodTechniqueCandidate,
    MethodTechniqueKind,
    NormalizedHeading,
    NormalizedItem,
    NormalizedList,
    NormalizedTable,
    NormalizedText,
)

_SECTION_SIGNAL = re.compile(r"\b(methods?|techniques?)\b", re.IGNORECASE)
_TABLE_SIGNAL = re.compile(
    r"\b(methods?|techniques?|measures?|procedures?|approaches?)\b", re.IGNORECASE
)
_PREFIX = re.compile(r"^(?:[A-Z]?\.?\d+(?:\.\d+)*|[a-zA-Z]|[-–—•])\s*[.):;-]?\s+")
_RECOMMENDATION_MARKER = re.compile(r"^(?:HR|R|—|-|NR)\s*$", re.IGNORECASE)


class MethodTechniqueExtractor:
    """Build a conservative candidate index from normalized lists and tables.

    The extractor deliberately favors precision. It only registers entries found under a
    heading, caption, or table header that explicitly identifies methods or techniques.
    """

    def extract(self, items: tuple[NormalizedItem, ...]) -> tuple[MethodTechniqueCandidate, ...]:
        candidates: list[MethodTechniqueCandidate] = []
        active_heading: NormalizedHeading | None = None

        for item in items:
            if isinstance(item, NormalizedHeading):
                active_heading = item
                continue

            heading_signal = active_heading.text if active_heading else ""
            if isinstance(item, NormalizedList) and _has_signal(heading_signal):
                kind = _kind_from_context(heading_signal)
                for entry in _flatten_list(item):
                    candidate = _candidate(
                        name=entry,
                        kind=kind,
                        source_item_ids=item.source_item_ids,
                        context=heading_signal,
                        rule_id="methods.list-under-signalled-heading",
                        confidence=0.9,
                    )
                    if candidate:
                        candidates.append(candidate)
                continue

            if isinstance(item, NormalizedTable):
                context = " ".join(part for part in (heading_signal, item.caption or "") if part)
                table_has_signal = _has_signal(context) or _table_header_has_signal(item)
                if table_has_signal:
                    kind = _kind_from_context(context or _table_header_text(item))
                    for name in _table_candidate_names(item):
                        candidate = _candidate(
                            name=name,
                            kind=kind,
                            source_item_ids=item.source_item_ids,
                            context=context or _table_header_text(item),
                            rule_id="methods.signalled-table-row",
                            confidence=0.95,
                        )
                        if candidate:
                            candidates.append(candidate)
                continue

            if isinstance(item, NormalizedText) and _has_signal(heading_signal):
                # Annexes sometimes encode one method per paragraph rather than a list.
                candidate = _candidate(
                    name=item.text,
                    kind=_kind_from_context(heading_signal),
                    source_item_ids=item.source_item_ids,
                    context=heading_signal,
                    rule_id="methods.text-under-signalled-heading",
                    confidence=0.7,
                )
                if candidate:
                    candidates.append(candidate)

        deduplicated: dict[tuple[str, MethodTechniqueKind], MethodTechniqueCandidate] = {}
        for candidate in candidates:
            key = (candidate.normalized_name, candidate.kind)
            previous = deduplicated.get(key)
            if previous is None:
                deduplicated[key] = candidate
                continue
            deduplicated[key] = previous.model_copy(
                update={
                    "source_item_ids": tuple(
                        dict.fromkeys((*previous.source_item_ids, *candidate.source_item_ids))
                    ),
                    "confidence": max(previous.confidence, candidate.confidence),
                }
            )
        return tuple(
            sorted(deduplicated.values(), key=lambda item: (item.normalized_name, item.id))
        )


def _flatten_list(item: NormalizedList) -> Iterable[str]:
    def walk(entries):
        for entry in entries:
            yield entry.text
            yield from walk(entry.children)

    return walk(item.items)


def _table_header_text(item: NormalizedTable) -> str:
    if not item.rows:
        return ""
    return " ".join(cell.text for cell in item.rows[0].cells)


def _table_header_has_signal(item: NormalizedTable) -> bool:
    return bool(_TABLE_SIGNAL.search(_table_header_text(item)))


def _table_candidate_names(item: NormalizedTable) -> Iterable[str]:
    for row_index, row in enumerate(item.rows):
        if not row.cells:
            continue
        if row_index == 0 and any(cell.is_header for cell in row.cells):
            continue
        values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
        if not values:
            continue
        name = next((value for value in values if not _RECOMMENDATION_MARKER.fullmatch(value)), "")
        if name:
            yield name


def _has_signal(value: str) -> bool:
    return bool(_SECTION_SIGNAL.search(value))


def _kind_from_context(value: str) -> MethodTechniqueKind:
    lower = value.casefold()
    has_method = "method" in lower
    has_technique = "technique" in lower
    if has_method and not has_technique:
        return MethodTechniqueKind.METHOD
    if has_technique and not has_method:
        return MethodTechniqueKind.TECHNIQUE
    return MethodTechniqueKind.METHOD_OR_TECHNIQUE


def _candidate(
    *,
    name: str,
    kind: MethodTechniqueKind,
    source_item_ids: tuple[str, ...],
    context: str,
    rule_id: str,
    confidence: float,
) -> MethodTechniqueCandidate | None:
    cleaned = _clean_name(name)
    if not _looks_like_name(cleaned):
        return None
    normalized = " ".join(cleaned.casefold().split())
    digest = hashlib.sha256(f"{kind}:{normalized}".encode()).hexdigest()[:16]
    return MethodTechniqueCandidate(
        id=f"method-technique:{digest}",
        name=cleaned,
        normalized_name=normalized,
        kind=kind,
        source_item_ids=source_item_ids,
        context=context.strip() or None,
        extraction_rule=rule_id,
        confidence=confidence,
    )


def _clean_name(value: str) -> str:
    value = " ".join(value.split())
    value = _PREFIX.sub("", value)
    return value.strip(" .;:–—-")


def _looks_like_name(value: str) -> bool:
    if not value or len(value) < 3 or len(value) > 180:
        return False
    if value.endswith((".", "?", "!")) and len(value.split()) > 12:
        return False
    return len(value.split()) <= 20
