"""Deterministic, provenance-preserving extracted document normalization."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from standards_atlas.application.model import (
    ExtractedCode,
    ExtractedDocument,
    ExtractedFormula,
    ExtractedHeading,
    ExtractedList,
    ExtractedPicture,
    ExtractedTable,
    ExtractedText,
    ExtractedUnknown,
)
from standards_atlas.application.model.normalized_document import (
    NormalizationMetadata,
    NormalizationOptions,
    NormalizationStatistics,
    NormalizedCode,
    NormalizedExtractedDocument,
    NormalizedFormula,
    NormalizedHeading,
    NormalizedItem,
    NormalizedList,
    NormalizedListItem,
    NormalizedPicture,
    NormalizedTable,
    NormalizedText,
    NormalizedUnknown,
    PageFurnitureDecision,
    SuppressedItem,
    TransformationEvent,
    TransformationLedger,
)
from standards_atlas.application.normalization.hyphenation import (
    merge_text_items,
    repair_hyphenation,
)
from standards_atlas.application.normalization.list_normalization import (
    LIST_MARKER as _LIST_MARKER,
)
from standards_atlas.application.normalization.list_normalization import (
    clause_reference_from_list_item,
    marker_is_ordered,
    normalize_list_marker,
    normalize_lists,
    reconstruct_list_hierarchy,
)
from standards_atlas.application.normalization.list_normalization import (
    looks_like_clause_reference as _list_looks_like_clause_reference,
)
from standards_atlas.application.normalization.method_technique_extractor import (
    MethodTechniqueExtractor,
)
from standards_atlas.application.normalization.pipeline import (
    DEFAULT_NORMALIZATION_STEPS,
    NormalizationRun,
)
from standards_atlas.application.normalization.text import (
    normalize_code,
    normalize_optional_text,
    normalize_text,
)
from standards_atlas.domain.model import ArtifactLineage, artifact_reference

NORMALIZER_VERSION = "0.8.0"

_PAGE_NUMBER = re.compile(r"^\s*(?:[-–—]\s*)?\d+(?:\s*[-–—])?\s*$")
_VARIABLE_NUMBER = re.compile(r"\d+")
_PROTECTED_CLAUSE_ANCHOR = re.compile(r"^(?:\d+(?:\.\d+)+|(?:[A-Z]|Z[A-Z])(?:\.\d+)*)(?:\s+|$)")


class DocumentNormalizer:
    """Normalize an extracted document without mutating its source representation."""

    def normalize(
        self,
        document: ExtractedDocument,
        options: NormalizationOptions | None = None,
    ) -> NormalizedExtractedDocument:
        options = options or NormalizationOptions()
        run = NormalizationRun(document=document, options=options)
        for step in DEFAULT_NORMALIZATION_STEPS:
            step.apply(run, self)
        page_furniture_decisions = run.page_furniture_decisions
        suppressed = run.suppressed
        events = run.events
        repaired_count = run.repaired_count
        merged_count = run.merged_count
        list_count = run.list_count
        resequenced = tuple(
            item.model_copy(
                update={
                    "id": _stable_normalized_item_id(document.source_id, item),
                    "sequence_number": index,
                }
            )
            for index, item in enumerate(run.items)
        )
        source_pages = {
            evidence.page_number
            for item in document.items
            for evidence in item.source_evidence
            if evidence.page_number is not None
        }
        selected_pages = {
            page
            for page in source_pages
            if _page_is_selected(
                page, options.page_ranges, options.exclude_page_ranges, options.page_list
            )
        }
        method_technique_candidates = MethodTechniqueExtractor().extract(resequenced)
        accounting = _account_source_items(document, resequenced, suppressed)
        statistics = NormalizationStatistics(
            input_items=len(document.items),
            output_items=len(resequenced),
            headers_suppressed=sum(item.reason == "header" for item in suppressed),
            footers_suppressed=sum(item.reason == "footer" for item in suppressed),
            page_numbers_suppressed=sum(item.reason == "page_number" for item in suppressed),
            hyphenations_repaired=repaired_count,
            text_fragments_merged=merged_count,
            lists_normalized=list_count,
            code_blocks=sum(isinstance(item, NormalizedCode) for item in resequenced),
            method_technique_candidates=len(method_technique_candidates),
            active_source_items=len(accounting.active_item_ids),
            suppressed_source_items=len(accounting.suppressed_item_ids),
            unaccounted_source_items=len(accounting.unaccounted_item_ids),
            duplicate_source_items=len(accounting.duplicate_item_ids),
            source_pages=len(source_pages),
            selected_pages=len(selected_pages),
            excluded_pages=len(source_pages - selected_pages),
        )
        if options.fail_on_data_loss and (
            accounting.unaccounted_item_ids or accounting.duplicate_item_ids
        ):
            from standards_atlas.application.normalization.errors import (
                NormalizationDataLossError,
            )

            raise NormalizationDataLossError(
                missing_item_ids=accounting.unaccounted_item_ids,
                duplicate_item_ids=accounting.duplicate_item_ids,
            )
        draft = NormalizedExtractedDocument(
            source_id=document.source_id,
            items=resequenced,
            suppressed_items=tuple(suppressed),
            page_furniture_decisions=page_furniture_decisions,
            transformation_ledger=TransformationLedger(events=tuple(events)),
            issues=(),
            method_technique_candidates=method_technique_candidates,
            metadata=NormalizationMetadata(
                normalizer_version=NORMALIZER_VERSION,
                source_extraction_hash=extracted_document_hash(document),
                options=options,
                statistics=statistics,
            ),
        )
        normalized_artifact = artifact_reference("normalized_document", draft)
        parents = (document.lineage.artifact,) if document.lineage else ()
        return draft.model_copy(
            update={
                "lineage": ArtifactLineage(
                    artifact=normalized_artifact,
                    derived_from=parents,
                    transformation_ids=tuple(event.id for event in events),
                )
            }
        )

    def _suppress_page_elements(
        self,
        document: ExtractedDocument,
        options: NormalizationOptions,
        page_furniture_decisions: tuple[PageFurnitureDecision, ...],
    ) -> tuple[list[SuppressedItem], list]:
        decisions = {decision.source_item_id: decision for decision in page_furniture_decisions}
        signatures = Counter(
            _page_signature(item.text)
            for item in document.items
            if isinstance(item, (ExtractedText, ExtractedHeading))
            and _item_is_selected(
                item, options.page_ranges, options.exclude_page_ranges, options.page_list
            )
        )
        suppressed: list[SuppressedItem] = []
        active = []
        for item in document.items:
            text = item.text if isinstance(item, (ExtractedText, ExtractedHeading)) else None
            reason = None
            confidence = 1.0
            protected_reference = text is not None and _looks_like_clause_anchor(text)
            if not _item_is_selected(
                item, options.page_ranges, options.exclude_page_ranges, options.page_list
            ):
                reason = "content_selection"
            elif text is not None and _PAGE_NUMBER.fullmatch(text) and not protected_reference:
                reason = "page_number"
            elif not protected_reference and item.id in decisions:
                decision = decisions[item.id]
                if decision.role == "page_header":
                    reason = "header"
                elif decision.role == "page_footer":
                    reason = "footer"
                elif decision.role == "page_number":
                    reason = "page_number"
                confidence = decision.confidence
            elif (
                options.suppress_repeated_page_elements
                and text is not None
                and not protected_reference
                and signatures[_page_signature(text)]
                >= options.repeated_page_element_min_occurrences
            ):
                zone = _page_zone(item)
                if options.suppress_headers and zone == "header":
                    reason, confidence = "header", 0.85
                elif options.suppress_footers and zone == "footer":
                    reason, confidence = "footer", 0.85
            if reason:
                suppressed.extend(
                    SuppressedItem(
                        source_item_id=source_item_id,
                        reason=reason,
                        confidence=confidence,
                        text=text,
                        page_number=_page_number(item),
                    )
                    for source_item_id in _source_unit_ids(item)
                )
            else:
                active.append(item)
        return suppressed, active

    def _map_items(self, item, options: NormalizationOptions) -> list[NormalizedItem]:
        if isinstance(item, ExtractedList):
            return self._map_list_items(item, options)
        return [self._map_item(item, options)]

    def _map_item(self, item, options: NormalizationOptions) -> NormalizedItem:
        common = dict(
            id=f"normalized:{item.id}",
            sequence_number=item.sequence_number,
            source_item_ids=(item.id,),
            source_evidence=item.source_evidence,
            original_labels=(item.original_label,) if item.original_label else (),
            layout_evidence=item.layout_evidence,
        )
        if isinstance(item, ExtractedCode):
            return NormalizedCode(
                **common,
                code=normalize_code(item.code, options),
                language=item.language,
            )
        if isinstance(item, ExtractedText):
            return NormalizedText(**common, text=normalize_text(item.text, options))
        if isinstance(item, ExtractedHeading):
            return NormalizedHeading(
                **common,
                text=normalize_text(item.text, options),
                observed_level=item.observed_level,
            )
        if isinstance(item, ExtractedTable):
            return NormalizedTable(
                **common,
                rows=item.rows,
                caption=normalize_optional_text(item.caption, options),
            )
        if isinstance(item, ExtractedPicture):
            return NormalizedPicture(
                **common,
                caption=normalize_optional_text(item.caption, options),
                description=normalize_optional_text(item.description, options),
                image_reference=item.image_reference,
                visual_asset=item.visual_asset,
            )
        if isinstance(item, ExtractedFormula):
            return NormalizedFormula(
                **common,
                expression=unicodedata.normalize(options.unicode_form, item.expression),
                original_expression=normalize_optional_text(item.original_expression, options),
                representation=item.representation,
                extraction_status=item.extraction_status,
            )
        if isinstance(item, ExtractedUnknown):
            return NormalizedUnknown(
                **common,
                text=normalize_optional_text(item.text, options),
                raw_attributes=item.raw_attributes,
            )
        raise TypeError(f"Unsupported extracted item: {type(item)!r}")

    def _map_list_items(
        self, item: ExtractedList, options: NormalizationOptions
    ) -> list[NormalizedItem]:
        """Keep ordinary lists grouped but expose clause-like entries as top-level items."""
        output: list[NormalizedItem] = []
        ordinary_run = []

        def flush_ordinary_run() -> None:
            if not ordinary_run:
                return
            first_index, first_entry = ordinary_run[0]
            source_ids = tuple(
                entry.id or f"{item.id}:item:{index}" for index, entry in ordinary_run
            )
            evidence = (
                tuple(
                    source_evidence
                    for _, entry in ordinary_run
                    for source_evidence in entry.source_evidence
                )
                or item.source_evidence
            )
            output.append(
                NormalizedList(
                    id=f"normalized-list:{source_ids[0]}",
                    sequence_number=item.sequence_number + first_index,
                    source_item_ids=source_ids,
                    source_evidence=evidence,
                    original_labels=item.original_label and (item.original_label,) or (),
                    layout_evidence=tuple(
                        layout for _, entry in ordinary_run for layout in entry.layout_evidence
                    )
                    or item.layout_evidence,
                    ordered=item.ordered,
                    items=reconstruct_list_hierarchy(
                        tuple(
                            NormalizedListItem(
                                text=normalize_text(entry.text, options),
                                marker=normalize_list_marker(entry.marker),
                                ordered=marker_is_ordered(entry.marker),
                                source_item_ids=(entry.id or f"{item.id}:item:{index}",),
                                source_evidence=entry.source_evidence,
                                layout_evidence=entry.layout_evidence,
                            )
                            for index, entry in ordinary_run
                        )
                    ),
                )
            )
            ordinary_run.clear()

        for index, entry in enumerate(item.items):
            text = normalize_text(entry.text, options)
            marker = normalize_list_marker(entry.marker)
            source_id = entry.id or f"{item.id}:item:{index}"
            clause_reference, reference_is_in_text = clause_reference_from_list_item(
                marker,
                text,
            )
            if clause_reference is not None:
                flush_ordinary_run()
                clause_text = text if reference_is_in_text else clause_reference
                if text and not reference_is_in_text:
                    clause_text = f"{clause_reference} {text}"
                output.append(
                    NormalizedText(
                        id=f"normalized:{source_id}",
                        sequence_number=item.sequence_number + index,
                        source_item_ids=(source_id,),
                        source_evidence=entry.source_evidence or item.source_evidence,
                        original_labels=(item.original_label,) if item.original_label else (),
                        layout_evidence=entry.layout_evidence or item.layout_evidence,
                        text=clause_text,
                    )
                )
            else:
                ordinary_run.append((index, entry))
        flush_ordinary_run()
        return output

    def _repair_hyphenation(
        self, items: list[NormalizedItem], options: NormalizationOptions
    ) -> tuple[list[NormalizedItem], int, list[TransformationEvent]]:
        return repair_hyphenation(items, options, _transformation_event)

    def _merge_text_fragments(
        self, items: list[NormalizedItem], options: NormalizationOptions
    ) -> tuple[list[NormalizedItem], int, list[TransformationEvent]]:
        if not options.merge_text_fragments:
            return items, 0, []
        output: list[NormalizedItem] = []
        merged = 0
        events: list[TransformationEvent] = []
        for item in items:
            if (
                output
                and isinstance(output[-1], NormalizedText)
                and isinstance(item, NormalizedText)
            ):
                previous = output[-1]
                if _should_merge(previous.text, item.text):
                    merged_item = merge_text_items(previous, item, f"{previous.text} {item.text}")
                    output[-1] = merged_item
                    events.append(
                        _transformation_event(
                            stage="text_merge",
                            rule_id="normalize.text.merge-continuation",
                            action="merge",
                            source_item_ids=merged_item.source_item_ids,
                            output_item_ids=(merged_item.id,),
                            rationale="Adjacent text fragments form one prose continuation.",
                        )
                    )
                    merged += 1
                    continue
            output.append(item)
        return output, merged, events

    def _normalize_lists(
        self, items: list[NormalizedItem], options: NormalizationOptions
    ) -> tuple[list[NormalizedItem], int, list[TransformationEvent]]:
        return normalize_lists(items, options, _transformation_event)


def _selection_events(
    suppressed_items: list[SuppressedItem],
    decisions: tuple[PageFurnitureDecision, ...],
) -> list[TransformationEvent]:
    decision_by_id = {decision.source_item_id: decision for decision in decisions}
    events: list[TransformationEvent] = []
    for item in suppressed_items:
        decision = decision_by_id.get(item.source_item_id)
        rule_id = (
            decision.rule_id
            if decision is not None
            else f"normalize.selection.{item.reason.replace('_', '-')}"
        )
        rationale = {
            "header": "The source item is classified as repeated page-header furniture.",
            "footer": "The source item is classified as repeated page-footer furniture.",
            "page_number": "The source item is classified as a page number.",
            "content_selection": "The source item lies outside the selected page content.",
        }[item.reason]
        events.append(
            _transformation_event(
                stage="selection",
                rule_id=rule_id,
                action="suppress",
                source_item_ids=(item.source_item_id,),
                rationale=rationale,
                details={"reason": item.reason, "confidence": item.confidence},
            )
        )
    return events


def _mapping_events(items: list[NormalizedItem]) -> list[TransformationEvent]:
    return [
        _transformation_event(
            stage="mapping",
            rule_id=f"normalize.map.{item.type}",
            action="map",
            source_item_ids=item.source_item_ids,
            output_item_ids=(item.id,),
            rationale="The extracted observation is mapped without semantic reinterpretation.",
        )
        for item in items
    ]


def _transformation_event(
    *,
    stage: str,
    rule_id: str,
    action: str,
    source_item_ids: tuple[str, ...],
    rationale: str,
    output_item_ids: tuple[str, ...] = (),
    details: dict[str, object] | None = None,
) -> TransformationEvent:
    payload = {
        "stage": stage,
        "rule_id": rule_id,
        "action": action,
        "source_item_ids": source_item_ids,
        "output_item_ids": output_item_ids,
        "rationale": rationale,
        "details": details or {},
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return TransformationEvent(id=f"tx:{digest}", **payload)


@dataclass(frozen=True)
class _SourceAccounting:
    active_item_ids: tuple[str, ...]
    suppressed_item_ids: tuple[str, ...]
    unaccounted_item_ids: tuple[str, ...]
    duplicate_item_ids: tuple[str, ...]


def _source_unit_ids(item: object) -> tuple[str, ...]:
    """Return the independently traceable source identities of an extracted item."""
    if isinstance(item, ExtractedList) and item.items:
        return tuple(
            entry.id or f"{item.id}:item:{index}" for index, entry in enumerate(item.items)
        )
    return (item.id,)


def _account_source_items(
    document: ExtractedDocument,
    normalized_items: tuple[NormalizedItem, ...],
    suppressed_items: list[SuppressedItem],
) -> _SourceAccounting:
    expected = tuple(source_id for item in document.items for source_id in _source_unit_ids(item))
    active_occurrences = tuple(
        source_id for item in normalized_items for source_id in item.source_item_ids
    )
    suppressed_occurrences = tuple(item.source_item_id for item in suppressed_items)
    occurrence_counts = Counter(active_occurrences + suppressed_occurrences)
    expected_counts = Counter(expected)

    unaccounted = tuple(
        source_id for source_id in dict.fromkeys(expected) if occurrence_counts[source_id] == 0
    )
    duplicate = tuple(
        source_id
        for source_id in dict.fromkeys(expected)
        if occurrence_counts[source_id] > 1 or expected_counts[source_id] > 1
    )
    return _SourceAccounting(
        active_item_ids=tuple(
            source_id for source_id in dict.fromkeys(expected) if source_id in active_occurrences
        ),
        suppressed_item_ids=tuple(
            source_id
            for source_id in dict.fromkeys(expected)
            if source_id in suppressed_occurrences
        ),
        unaccounted_item_ids=unaccounted,
        duplicate_item_ids=duplicate,
    )


def _stable_normalized_item_id(source_id: str, item: NormalizedItem) -> str:
    """Derive identity from source lineage and normalized item kind, not run order."""
    payload = json.dumps(
        {
            "source_id": source_id,
            "type": item.type,
            "source_item_ids": list(item.source_item_ids),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"normalized:{hashlib.sha256(payload).hexdigest()}"


def extracted_document_hash(document: ExtractedDocument) -> str:
    payload = document.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _page_signature(text: str) -> str:
    normalized = " ".join(text.split())
    if _looks_like_clause_reference(normalized):
        return normalized.casefold()
    return _VARIABLE_NUMBER.sub("<NUMBER>", normalized.casefold())


def _looks_like_clause_reference(text: str) -> bool:
    return _list_looks_like_clause_reference(text)


def _looks_like_clause_anchor(text: str) -> bool:
    normalized = " ".join(text.split())
    return bool(_PROTECTED_CLAUSE_ANCHOR.match(normalized))


def _page_number(item) -> int | None:
    for evidence in item.source_evidence:
        if evidence.page_number is not None:
            return evidence.page_number
    return None


def _page_zone(item) -> str | None:
    boxes = [evidence.bounding_box for evidence in item.source_evidence if evidence.bounding_box]
    if not boxes:
        return None
    box = boxes[0]
    if box.coordinate_origin.value == "bottom_left":
        if box.bottom >= 700:
            return "header"
        if box.top <= 80:
            return "footer"
        return None
    if box.top <= 80:
        return "header"
    if box.bottom >= 700:
        return "footer"
    return None


def _should_merge(previous: str, current: str) -> bool:
    return bool(
        previous
        and current
        and not _LIST_MARKER.match(previous)
        and not _LIST_MARKER.match(current)
        and previous[-1] not in ".:;!?"
        and current[0].islower()
        and not _looks_like_clause_reference(previous)
        and not _looks_like_clause_reference(current)
    )


def _page_is_selected(
    page_number: int,
    page_ranges: tuple[tuple[int, int | None], ...],
    exclude_page_ranges: tuple[tuple[int, int | None], ...] = (),
    page_list: tuple[int, ...] = (),
) -> bool:
    has_positive_selection = bool(page_ranges or page_list)
    included = (
        not has_positive_selection
        or page_number in page_list
        or any(
            page_number >= start and (end is None or page_number <= end)
            for start, end in page_ranges
        )
    )
    excluded = any(
        page_number >= start and (end is None or page_number <= end)
        for start, end in exclude_page_ranges
    )
    return included and not excluded


def _item_is_selected(
    item: object,
    page_ranges: tuple[tuple[int, int | None], ...],
    exclude_page_ranges: tuple[tuple[int, int | None], ...] = (),
    page_list: tuple[int, ...] = (),
) -> bool:
    if not page_ranges and not exclude_page_ranges and not page_list:
        return True
    evidence = getattr(item, "source_evidence", ())
    pages = [entry.page_number for entry in evidence if entry.page_number is not None]
    # Keep items without page provenance: dropping them would violate lossless normalization.
    return not pages or any(
        _page_is_selected(page, page_ranges, exclude_page_ranges, page_list) for page in pages
    )
