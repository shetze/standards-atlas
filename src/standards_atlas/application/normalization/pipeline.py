"""Explicit normalization pipeline steps.

Each step performs one deterministic transformation and records its ledger events.
The steps intentionally operate on a small mutable run state while the public
normalizer remains immutable from the caller's perspective.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from standards_atlas.application.model import ExtractedDocument
from standards_atlas.application.model.normalized_document import (
    NormalizationOptions,
    PageFurnitureDecision,
    SuppressedItem,
    TransformationEvent,
)


@dataclass
class NormalizationRun:
    document: ExtractedDocument
    options: NormalizationOptions
    page_furniture_decisions: tuple[PageFurnitureDecision, ...] = ()
    suppressed: list[SuppressedItem] = field(default_factory=list)
    items: list[Any] = field(default_factory=list)
    events: list[TransformationEvent] = field(default_factory=list)
    repaired_count: int = 0
    merged_count: int = 0
    list_count: int = 0


class NormalizationOperations(Protocol):
    def _suppress_page_elements(
        self,
        document: ExtractedDocument,
        options: NormalizationOptions,
        page_furniture_decisions: tuple[PageFurnitureDecision, ...],
    ) -> tuple[list[SuppressedItem], list[Any]]: ...
    def _map_items(
        self, item: Any, options: NormalizationOptions
    ) -> tuple[Any, ...] | list[Any]: ...
    def _repair_hyphenation(
        self, items: list[Any], options: NormalizationOptions
    ) -> tuple[list[Any], int, list[TransformationEvent]]: ...
    def _merge_text_fragments(
        self, items: list[Any], options: NormalizationOptions
    ) -> tuple[list[Any], int, list[TransformationEvent]]: ...
    def _normalize_lists(
        self, items: list[Any], options: NormalizationOptions
    ) -> tuple[list[Any], int, list[TransformationEvent]]: ...


class NormalizationStep(Protocol):
    def apply(self, run: NormalizationRun, operations: NormalizationOperations) -> None: ...


class PageFurnitureSelectionStep:
    def apply(self, run: NormalizationRun, operations: NormalizationOperations) -> None:
        from standards_atlas.application.normalization.document_normalizer import _selection_events
        from standards_atlas.application.normalization.page_furniture_classifier import (
            PageFurnitureClassifier,
        )

        run.page_furniture_decisions = PageFurnitureClassifier().classify(run.document, run.options)
        run.suppressed, active = operations._suppress_page_elements(
            run.document, run.options, run.page_furniture_decisions
        )
        run.items = active
        run.events.extend(_selection_events(run.suppressed, run.page_furniture_decisions))


class ItemMappingStep:
    def apply(self, run: NormalizationRun, operations: NormalizationOperations) -> None:
        from standards_atlas.application.normalization.document_normalizer import _mapping_events

        run.items = [
            normalized_item
            for item in run.items
            for normalized_item in operations._map_items(item, run.options)
        ]
        run.events.extend(_mapping_events(run.items))


class HyphenationRepairStep:
    def apply(self, run: NormalizationRun, operations: NormalizationOperations) -> None:
        run.items, run.repaired_count, events = operations._repair_hyphenation(
            run.items, run.options
        )
        run.events.extend(events)


class TextFragmentMergeStep:
    def apply(self, run: NormalizationRun, operations: NormalizationOperations) -> None:
        run.items, run.merged_count, events = operations._merge_text_fragments(
            run.items, run.options
        )
        run.events.extend(events)


class ListNormalizationStep:
    def apply(self, run: NormalizationRun, operations: NormalizationOperations) -> None:
        run.items, run.list_count, events = operations._normalize_lists(run.items, run.options)
        run.events.extend(events)


DEFAULT_NORMALIZATION_STEPS: tuple[NormalizationStep, ...] = (
    PageFurnitureSelectionStep(),
    ItemMappingStep(),
    HyphenationRepairStep(),
    TextFragmentMergeStep(),
    ListNormalizationStep(),
)
