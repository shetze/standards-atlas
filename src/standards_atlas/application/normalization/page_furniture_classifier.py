"""Deterministic classification of repeated page furniture."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import median
from typing import Literal

from standards_atlas.application.model.extracted_document import (
    ExtractedDocument,
    ExtractedHeading,
    ExtractedItem,
    ExtractedText,
)
from standards_atlas.application.model.normalized_document import (
    NormalizationOptions,
    PageFurnitureDecision,
)
from standards_atlas.domain.model import CoordinateOrigin

_PAGE_NUMBER = re.compile(r"^\s*(?:[-–—]\s*)?\d+(?:\s*[-–—])?\s*$")
_VARIABLE_NUMBER = re.compile(r"\d+")
_CLAUSE_REFERENCE = re.compile(r"^(?:\d+(?:\.\d+)+|[A-Z]{1,3}(?:\.\d+)*)$")
_PROTECTED_CLAUSE_ANCHOR = re.compile(r"^(?:\d+(?:\.\d+)+|(?:[A-Z]|Z[A-Z])(?:\.\d+)*)(?:\s+|$)")


@dataclass(frozen=True)
class _ObservedText:
    item_id: str
    text: str
    original_label: str | None
    page_number: int | None
    page_height: float | None
    top_margin_ratio: float | None
    bottom_margin_ratio: float | None


class PageFurnitureClassifier:
    """Classify page headers, footers and page numbers from layout evidence."""

    def classify(
        self,
        document: ExtractedDocument,
        options: NormalizationOptions,
    ) -> tuple[PageFurnitureDecision, ...]:
        observations = tuple(
            observation
            for item in document.items
            if _is_textual(item)
            if (observation := _observe(item)) is not None and _item_is_selected(item, options)
        )
        grouped: dict[str, list[_ObservedText]] = defaultdict(list)
        for observation in observations:
            grouped[_signature(observation.text)].append(observation)

        decisions: list[PageFurnitureDecision] = []
        for observation in observations:
            if _PAGE_NUMBER.fullmatch(observation.text) and not _looks_like_clause_anchor(
                observation.text
            ):
                decisions.append(
                    _decision(
                        observation,
                        role="page_number",
                        rule_id="page-number-pattern",
                        confidence=1.0,
                        occurrences=1,
                        distinct_pages=1 if observation.page_number is not None else 0,
                        position_ratio=None,
                    )
                )
                continue

            peers = grouped[_signature(observation.text)]
            repeated = _repeated_margin_classification(peers, options)
            if repeated is None or _looks_like_clause_anchor(observation.text):
                continue
            role, confidence, position_ratio = repeated
            if role == "page_header" and not options.suppress_headers:
                continue
            if role == "page_footer" and not options.suppress_footers:
                continue
            decisions.append(
                _decision(
                    observation,
                    role=role,
                    rule_id="repeated-margin-text",
                    confidence=confidence,
                    occurrences=len(peers),
                    distinct_pages=len(
                        {peer.page_number for peer in peers if peer.page_number is not None}
                    ),
                    position_ratio=position_ratio,
                )
            )
        return tuple(sorted(decisions, key=lambda decision: decision.source_item_id))


def _repeated_margin_classification(
    observations: Iterable[_ObservedText],
    options: NormalizationOptions,
) -> tuple[Literal["page_header", "page_footer"], float, float] | None:
    observations = tuple(observations)
    pages = {item.page_number for item in observations if item.page_number is not None}
    if len(observations) < options.repeated_page_element_min_occurrences:
        return None
    if len(pages) < options.repeated_page_element_min_occurrences:
        return None

    explicit_roles = {item.original_label for item in observations}
    if explicit_roles == {"page_header"}:
        return (
            "page_header",
            0.95,
            median(
                [ratio for item in observations if (ratio := item.top_margin_ratio) is not None]
                or [0.0]
            ),
        )
    if explicit_roles == {"page_footer"}:
        return (
            "page_footer",
            0.95,
            median(
                [ratio for item in observations if (ratio := item.bottom_margin_ratio) is not None]
                or [0.0]
            ),
        )

    top_ratios = [
        item.top_margin_ratio for item in observations if item.top_margin_ratio is not None
    ]
    bottom_ratios = [
        item.bottom_margin_ratio for item in observations if item.bottom_margin_ratio is not None
    ]
    required_positioned = max(
        options.repeated_page_element_min_occurrences,
        int(len(observations) * 0.8 + 0.999),
    )
    if len(top_ratios) >= required_positioned:
        top_median = median(top_ratios)
        if top_median <= 0.12 and _cluster_span(top_ratios) <= 0.04:
            return "page_header", _confidence(observations, top_ratios), top_median
    if len(bottom_ratios) >= required_positioned:
        bottom_median = median(bottom_ratios)
        if bottom_median <= 0.12 and _cluster_span(bottom_ratios) <= 0.04:
            return "page_footer", _confidence(observations, bottom_ratios), bottom_median
    return None


def _confidence(observations: tuple[_ObservedText, ...], ratios: list[float]) -> float:
    positioned_ratio = len(ratios) / len(observations)
    distinct_pages = {item.page_number for item in observations if item.page_number is not None}
    page_ratio = len(distinct_pages) / len(observations)
    compactness = max(0.0, 1.0 - (_cluster_span(ratios) / 0.04))
    confidence = 0.8 + 0.1 * positioned_ratio + 0.05 * page_ratio + 0.04 * compactness
    return round(min(0.99, confidence), 3)


def _cluster_span(values: list[float]) -> float:
    if not values:
        return 1.0
    return max(values) - min(values)


def _observe(item: ExtractedText | ExtractedHeading) -> _ObservedText | None:
    evidence = next((entry for entry in item.source_evidence if entry.bounding_box), None)
    layout = item.layout_evidence[0] if item.layout_evidence else None
    page_number = next(
        (entry.page_number for entry in item.source_evidence if entry.page_number is not None),
        None,
    )
    page_height = layout.page_height if layout is not None else None
    top_ratio = None
    bottom_ratio = None
    if evidence is not None and page_height:
        box = evidence.bounding_box
        if box is not None:
            if box.coordinate_origin == CoordinateOrigin.BOTTOM_LEFT:
                top_ratio = max(0.0, page_height - box.bottom) / page_height
                bottom_ratio = max(0.0, box.top) / page_height
            else:
                top_ratio = max(0.0, box.top) / page_height
                bottom_ratio = max(0.0, page_height - box.bottom) / page_height
    return _ObservedText(
        item_id=item.id,
        text=item.text,
        original_label=item.original_label,
        page_number=page_number,
        page_height=page_height,
        top_margin_ratio=top_ratio,
        bottom_margin_ratio=bottom_ratio,
    )


def _decision(
    observation: _ObservedText,
    *,
    role: Literal["page_header", "page_footer", "page_number"],
    rule_id: str,
    confidence: float,
    occurrences: int,
    distinct_pages: int,
    position_ratio: float | None,
) -> PageFurnitureDecision:
    return PageFurnitureDecision(
        source_item_id=observation.item_id,
        role=role,
        rule_id=rule_id,
        confidence=confidence,
        text=observation.text,
        original_label=observation.original_label,
        page_number=observation.page_number,
        signature=_signature(observation.text),
        occurrences=occurrences,
        distinct_pages=distinct_pages,
        margin_position_ratio=position_ratio,
    )


def _signature(text: str) -> str:
    normalized = " ".join(text.split())
    if _CLAUSE_REFERENCE.fullmatch("".join(normalized.split())):
        return normalized.casefold()
    return _VARIABLE_NUMBER.sub("<NUMBER>", normalized.casefold())


def _looks_like_clause_anchor(text: str) -> bool:
    return bool(_PROTECTED_CLAUSE_ANCHOR.match(" ".join(text.split())))


def _is_textual(item: ExtractedItem) -> bool:
    return isinstance(item, (ExtractedText, ExtractedHeading))


def _item_is_selected(item: ExtractedItem, options: NormalizationOptions) -> bool:
    if not options.page_ranges and not options.exclude_page_ranges and not options.page_list:
        return True
    pages = [entry.page_number for entry in item.source_evidence if entry.page_number is not None]
    return not pages or any(_page_is_selected(page, options) for page in pages)


def _page_is_selected(page: int, options: NormalizationOptions) -> bool:
    has_positive = bool(options.page_ranges or options.page_list)
    included = (
        not has_positive
        or page in options.page_list
        or any(page >= start and (end is None or page <= end) for start, end in options.page_ranges)
    )
    excluded = any(
        page >= start and (end is None or page <= end) for start, end in options.exclude_page_ranges
    )
    return included and not excluded
