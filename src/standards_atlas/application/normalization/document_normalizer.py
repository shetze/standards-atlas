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
from standards_atlas.application.normalization.page_furniture_classifier import (
    PageFurnitureClassifier,
)
from standards_atlas.domain.model import ArtifactLineage, artifact_reference

NORMALIZER_VERSION = "0.7.0"

_LIST_MARKER = re.compile(r"^\s*((?:\d+|[A-Za-z]|[ivxlcdmIVXLCDM]+)[.)]|[-–—•])\s+(.+)$")
_PAGE_NUMBER = re.compile(r"^\s*(?:[-–—]\s*)?\d+(?:\s*[-–—])?\s*$")
_VARIABLE_NUMBER = re.compile(r"\d+")
_CLAUSE_REFERENCE = re.compile(r"^(?:\d+(?:\.\d+)+|[A-Z]{1,3}(?:\.\d+)*)$")
_CLAUSE_REFERENCE_START = re.compile(r"^(?:\d+(?:\.\d+)+|[A-Z]{1,3}(?:\.\d+)*)(?:\s+|$)")
_PROTECTED_CLAUSE_ANCHOR = re.compile(r"^(?:\d+(?:\.\d+)+|(?:[A-Z]|Z[A-Z])(?:\.\d+)*)(?:\s+|$)")
_LOWERCASE_START = re.compile(r"^[a-zà-öø-ÿ]")


class DocumentNormalizer:
    """Normalize an extracted document without mutating its source representation."""

    def normalize(
        self,
        document: ExtractedDocument,
        options: NormalizationOptions | None = None,
    ) -> NormalizedExtractedDocument:
        options = options or NormalizationOptions()
        page_furniture_decisions = PageFurnitureClassifier().classify(document, options)
        suppressed, active = self._suppress_page_elements(
            document, options, page_furniture_decisions
        )
        events = _selection_events(suppressed, page_furniture_decisions)
        mapped = [
            normalized_item for item in active for normalized_item in self._map_items(item, options)
        ]
        events.extend(_mapping_events(mapped))
        repaired, repaired_count, repair_events = self._repair_hyphenation(mapped, options)
        events.extend(repair_events)
        merged, merged_count, merge_events = self._merge_text_fragments(repaired, options)
        events.extend(merge_events)
        listed, list_count, list_events = self._normalize_lists(merged, options)
        events.extend(list_events)
        resequenced = tuple(
            item.model_copy(
                update={
                    "id": _stable_normalized_item_id(document.source_id, item),
                    "sequence_number": index,
                }
            )
            for index, item in enumerate(listed)
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
                code=_normalize_code(item.code, options),
                language=item.language,
            )
        if isinstance(item, ExtractedText):
            return NormalizedText(**common, text=_normalize_text(item.text, options))
        if isinstance(item, ExtractedHeading):
            return NormalizedHeading(
                **common,
                text=_normalize_text(item.text, options),
                observed_level=item.observed_level,
            )
        if isinstance(item, ExtractedTable):
            return NormalizedTable(
                **common,
                rows=item.rows,
                caption=_optional_text(item.caption, options),
            )
        if isinstance(item, ExtractedPicture):
            return NormalizedPicture(
                **common,
                caption=_optional_text(item.caption, options),
                description=_optional_text(item.description, options),
                image_reference=item.image_reference,
                visual_asset=item.visual_asset,
            )
        if isinstance(item, ExtractedFormula):
            return NormalizedFormula(
                **common,
                expression=unicodedata.normalize(options.unicode_form, item.expression),
                original_expression=_optional_text(item.original_expression, options),
                representation=item.representation,
                extraction_status=item.extraction_status,
            )
        if isinstance(item, ExtractedUnknown):
            return NormalizedUnknown(
                **common,
                text=_optional_text(item.text, options),
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
                    items=_reconstruct_list_hierarchy(
                        tuple(
                            NormalizedListItem(
                                text=_normalize_text(entry.text, options),
                                marker=_normalize_list_marker(entry.marker),
                                ordered=_marker_is_ordered(entry.marker),
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
            text = _normalize_text(entry.text, options)
            marker = _normalize_list_marker(entry.marker)
            source_id = entry.id or f"{item.id}:item:{index}"
            clause_reference, reference_is_in_text = _clause_reference_from_list_item(
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
        if not options.repair_hyphenation:
            return items, 0, []
        output: list[NormalizedItem] = []
        repaired = 0
        events: list[TransformationEvent] = []
        index = 0
        while index < len(items):
            current = items[index]
            if (
                index + 1 < len(items)
                and isinstance(current, NormalizedText)
                and isinstance(items[index + 1], NormalizedText)
                and current.text.endswith("-")
                and _LOWERCASE_START.match(items[index + 1].text)
            ):
                following = items[index + 1]
                repaired_item = _merge_text_items(
                    current,
                    following,
                    current.text[:-1] + following.text,
                )
                output.append(repaired_item)
                events.append(
                    _transformation_event(
                        stage="hyphenation",
                        rule_id="normalize.hyphenation.cross-item-lowercase",
                        action="repair",
                        source_item_ids=repaired_item.source_item_ids,
                        output_item_ids=(repaired_item.id,),
                        rationale="A trailing hyphen joins a lowercase continuation.",
                    )
                )
                repaired += 1
                index += 2
                continue
            if isinstance(current, NormalizedText):
                text, count = re.subn(r"(?<=\w)-\s*\n\s*(?=[a-zà-öø-ÿ])", "", current.text)
                if count:
                    current = current.model_copy(update={"text": text})
                    events.append(
                        _transformation_event(
                            stage="hyphenation",
                            rule_id="normalize.hyphenation.intra-item-lowercase",
                            action="repair",
                            source_item_ids=current.source_item_ids,
                            output_item_ids=(current.id,),
                            rationale="Line-break hyphenation precedes a lowercase continuation.",
                            details={"repairs": count},
                        )
                    )
                    repaired += count
            output.append(current)
            index += 1
        return output, repaired, events

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
                    merged_item = _merge_text_items(previous, item, f"{previous.text} {item.text}")
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
                    merged_list = _merge_lists(lists)
                    output.append(merged_list)
                    events.append(
                        _transformation_event(
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
                match = _LIST_MARKER.match(items[cursor].text)
                if not match:
                    break
                run.append((items[cursor], match))
                cursor += 1
            if len(run) >= 2:
                markers = [match.group(1) for _, match in run]
                ordered = all(marker[0].isalnum() for marker in markers)
                first = run[0][0]
                output.append(
                    NormalizedList(
                        id=f"normalized-list:{first.id}",
                        sequence_number=first.sequence_number,
                        source_item_ids=tuple(
                            source_id for item, _ in run for source_id in item.source_item_ids
                        ),
                        source_evidence=tuple(
                            evidence for item, _ in run for evidence in item.source_evidence
                        ),
                        original_labels=tuple(
                            label for item, _ in run for label in item.original_labels
                        ),
                        layout_evidence=tuple(
                            layout for item, _ in run for layout in item.layout_evidence
                        ),
                        ordered=ordered,
                        items=_reconstruct_list_hierarchy(
                            tuple(
                                NormalizedListItem(
                                    text=match.group(2),
                                    marker=match.group(1),
                                    ordered=_marker_is_ordered(match.group(1)),
                                    source_item_ids=item.source_item_ids,
                                    source_evidence=item.source_evidence,
                                    layout_evidence=item.layout_evidence,
                                )
                                for item, match in run
                            )
                        ),
                    )
                )
                normalized_list = output[-1]
                events.append(
                    _transformation_event(
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


@dataclass
class _MutableListItem:
    item: NormalizedListItem
    children: list[_MutableListItem]


def _reconstruct_list_hierarchy(
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


def _list_item_left(item: NormalizedListItem) -> float | None:
    for evidence in item.source_evidence:
        if evidence.bounding_box is not None:
            return evidence.bounding_box.left
    for layout in item.layout_evidence:
        # LayoutEvidence deliberately contains no duplicate bbox; source evidence is canonical.
        if layout.group_path:
            continue
    return None


def _indentation_depth(position: float | None, levels: list[float]) -> int:
    if position is None:
        return 0
    return min(range(len(levels)), key=lambda index: abs(levels[index] - position))


def _freeze_list_item(node: _MutableListItem) -> NormalizedListItem:
    return node.item.model_copy(
        update={"children": tuple(_freeze_list_item(child) for child in node.children)}
    )


def _marker_is_ordered(marker: str | None) -> bool:
    normalized = _normalize_list_marker(marker)
    return bool(normalized and normalized[0].isalnum())


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


def _normalize_list_marker(value: str | None) -> str | None:
    if value is None:
        return None
    marker = "".join(value.split()).rstrip(".)")
    return marker or None


def _clause_reference_from_list_item(
    marker: str | None,
    text: str,
) -> tuple[str | None, bool]:
    if marker is not None and _CLAUSE_REFERENCE.fullmatch(marker):
        return marker, False
    match = _CLAUSE_REFERENCE_START.match(text)
    if match is None:
        return None, False
    return match.group(0).strip(), True


def _normalize_text(value: str, options: NormalizationOptions) -> str:
    value = unicodedata.normalize(options.unicode_form, value)
    value = "".join(
        character
        for character in value
        if character in "\n\t" or unicodedata.category(character) != "Cc"
    )
    value = value.replace("\u00a0", " ").replace("\u2007", " ").replace("\u202f", " ")
    if options.normalize_whitespace:
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\s*\n\s*", " ", value)
    return value.strip()


def _normalize_code(value: str, options: NormalizationOptions) -> str:
    value = (
        unicodedata.normalize(options.unicode_form, value).replace("\r\n", "\n").replace("\r", "\n")
    )
    return "".join(
        character
        for character in value
        if character in "\n\t" or unicodedata.category(character) != "Cc"
    ).strip("\n")


def _optional_text(value: str | None, options: NormalizationOptions) -> str | None:
    return _normalize_text(value, options) if value is not None else None


def _page_signature(text: str) -> str:
    normalized = " ".join(text.split())
    if _looks_like_clause_reference(normalized):
        return normalized.casefold()
    return _VARIABLE_NUMBER.sub("<NUMBER>", normalized.casefold())


def _looks_like_clause_reference(text: str) -> bool:
    return bool(_CLAUSE_REFERENCE.fullmatch("".join(text.split())))


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


def _merge_text_items(first: NormalizedText, second: NormalizedText, text: str) -> NormalizedText:
    return NormalizedText(
        id=f"{first.id}+{second.id}",
        sequence_number=first.sequence_number,
        source_item_ids=first.source_item_ids + second.source_item_ids,
        source_evidence=first.source_evidence + second.source_evidence,
        original_labels=first.original_labels + second.original_labels,
        layout_evidence=first.layout_evidence + second.layout_evidence,
        text=text,
    )


def _merge_lists(lists: list[NormalizedList]) -> NormalizedList:
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
