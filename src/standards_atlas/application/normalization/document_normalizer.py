"""Deterministic, provenance-preserving extracted document normalization."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime

from standards_atlas import __version__
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
    SuppressedItem,
)

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
        suppressed, active = self._suppress_page_elements(document, options)
        mapped = [
            normalized_item for item in active for normalized_item in self._map_items(item, options)
        ]
        repaired, repaired_count = self._repair_hyphenation(mapped, options)
        merged, merged_count = self._merge_text_fragments(repaired, options)
        listed, list_count = self._normalize_lists(merged, options)
        resequenced = tuple(
            item.model_copy(update={"sequence_number": index}) for index, item in enumerate(listed)
        )
        source_pages = {
            evidence.page_number
            for item in document.items
            for evidence in item.source_evidence
            if evidence.page_number is not None
        }
        selected_pages = {
            page for page in source_pages if _page_is_selected(page, options.page_ranges, options.exclude_page_ranges, options.page_list)
        }
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
            source_pages=len(source_pages),
            selected_pages=len(selected_pages),
            excluded_pages=len(source_pages - selected_pages),
        )
        return NormalizedExtractedDocument(
            source_id=document.source_id,
            items=resequenced,
            suppressed_items=tuple(suppressed),
            issues=(),
            metadata=NormalizationMetadata(
                normalizer_version=__version__,
                source_extraction_hash=extracted_document_hash(document),
                created_at=datetime.now(UTC),
                options=options,
                statistics=statistics,
            ),
        )

    def _suppress_page_elements(
        self,
        document: ExtractedDocument,
        options: NormalizationOptions,
    ) -> tuple[list[SuppressedItem], list]:
        signatures = Counter()
        for item in document.items:
            if (
                isinstance(item, (ExtractedText, ExtractedHeading))
                and _item_is_selected(item, options.page_ranges, options.exclude_page_ranges, options.page_list)
            ):
                signatures[_page_signature(item.text)] += 1
        suppressed: list[SuppressedItem] = []
        active = []
        for item in document.items:
            label = item.original_label or ""
            text = item.text if isinstance(item, (ExtractedText, ExtractedHeading)) else None
            reason = None
            confidence = 1.0
            protected_reference = text is not None and _looks_like_clause_anchor(text)
            if not _item_is_selected(item, options.page_ranges, options.exclude_page_ranges, options.page_list):
                reason = "content_selection"
            elif text is not None and _PAGE_NUMBER.fullmatch(text) and not protected_reference:
                reason = "page_number"
            elif options.suppress_headers and label == "page_header" and not protected_reference:
                reason = "header"
            elif options.suppress_footers and label == "page_footer" and not protected_reference:
                reason = "footer"
            elif (
                text is not None
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
                suppressed.append(
                    SuppressedItem(
                        source_item_id=item.id,
                        reason=reason,
                        confidence=confidence,
                        text=text,
                        page_number=_page_number(item),
                    )
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
            )
        if isinstance(item, ExtractedFormula):
            return NormalizedFormula(
                **common,
                expression=unicodedata.normalize(options.unicode_form, item.expression),
                representation=item.representation,
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
                    ordered=item.ordered,
                    items=tuple(
                        NormalizedListItem(
                            text=_normalize_text(entry.text, options),
                            marker=entry.marker,
                            source_item_ids=(entry.id or f"{item.id}:item:{index}",),
                        )
                        for index, entry in ordinary_run
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
                        text=clause_text,
                    )
                )
            else:
                ordinary_run.append((index, entry))
        flush_ordinary_run()
        return output

    def _repair_hyphenation(
        self, items: list[NormalizedItem], options: NormalizationOptions
    ) -> tuple[list[NormalizedItem], int]:
        if not options.repair_hyphenation:
            return items, 0
        output: list[NormalizedItem] = []
        repaired = 0
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
                output.append(
                    _merge_text_items(
                        current,
                        following,
                        current.text[:-1] + following.text,
                    )
                )
                repaired += 1
                index += 2
                continue
            if isinstance(current, NormalizedText):
                text, count = re.subn(r"(?<=\w)-\s*\n\s*(?=[a-zà-öø-ÿ])", "", current.text)
                if count:
                    current = current.model_copy(update={"text": text})
                    repaired += count
            output.append(current)
            index += 1
        return output, repaired

    def _merge_text_fragments(
        self, items: list[NormalizedItem], options: NormalizationOptions
    ) -> tuple[list[NormalizedItem], int]:
        if not options.merge_text_fragments:
            return items, 0
        output: list[NormalizedItem] = []
        merged = 0
        for item in items:
            if (
                output
                and isinstance(output[-1], NormalizedText)
                and isinstance(item, NormalizedText)
            ):
                previous = output[-1]
                if _should_merge(previous.text, item.text):
                    output[-1] = _merge_text_items(previous, item, f"{previous.text} {item.text}")
                    merged += 1
                    continue
            output.append(item)
        return output, merged

    def _normalize_lists(
        self, items: list[NormalizedItem], options: NormalizationOptions
    ) -> tuple[list[NormalizedItem], int]:
        if not options.normalize_lists:
            return items, 0
        output: list[NormalizedItem] = []
        index = 0
        normalized = 0
        while index < len(items):
            if isinstance(items[index], NormalizedList):
                lists = [items[index]]
                index += 1
                while index < len(items) and isinstance(items[index], NormalizedList):
                    lists.append(items[index])
                    index += 1
                if len(lists) > 1:
                    output.append(_merge_lists(lists))
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
                        source_item_ids=tuple(item.id for item, _ in run),
                        source_evidence=tuple(
                            evidence for item, _ in run for evidence in item.source_evidence
                        ),
                        original_labels=tuple(
                            label for item, _ in run for label in item.original_labels
                        ),
                        ordered=ordered,
                        items=tuple(
                            NormalizedListItem(
                                text=match.group(2),
                                marker=match.group(1),
                                source_item_ids=item.source_item_ids,
                            )
                            for item, match in run
                        ),
                    )
                )
                normalized += 1
                index = cursor
                continue
            output.append(items[index])
            index += 1
        return output, normalized


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
    included = not has_positive_selection or page_number in page_list or any(
        page_number >= start and (end is None or page_number <= end)
        for start, end in page_ranges
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
        _page_is_selected(page, page_ranges, exclude_page_ranges, page_list)
        for page in pages
    )
