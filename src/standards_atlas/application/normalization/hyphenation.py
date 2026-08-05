"""Deterministic hyphenation repair for normalized text items."""

from __future__ import annotations

import re
from typing import Protocol

from standards_atlas.application.model.normalized_document import (
    NormalizationOptions,
    NormalizedItem,
    NormalizedText,
    TransformationEvent,
)

_LOWERCASE_START = re.compile(r"^[a-zà-öø-ÿ]")


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


def repair_hyphenation(
    items: list[NormalizedItem],
    options: NormalizationOptions,
    event_factory: TransformationEventFactory,
) -> tuple[list[NormalizedItem], int, list[TransformationEvent]]:
    """Repair conservative lowercase hyphenation across and within items."""
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
            repaired_item = merge_text_items(
                current,
                following,
                current.text[:-1] + following.text,
            )
            output.append(repaired_item)
            events.append(
                event_factory(
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
                    event_factory(
                        stage="hyphenation",
                        rule_id="normalize.hyphenation.intra-item-lowercase",
                        action="repair",
                        source_item_ids=current.source_item_ids,
                        output_item_ids=(current.id,),
                        rationale=("Line-break hyphenation precedes a lowercase continuation."),
                        details={"repairs": count},
                    )
                )
                repaired += count
        output.append(current)
        index += 1
    return output, repaired, events


def merge_text_items(
    first: NormalizedText,
    second: NormalizedText,
    text: str,
) -> NormalizedText:
    """Merge two normalized text observations without losing provenance."""
    return NormalizedText(
        id=f"{first.id}+{second.id}",
        sequence_number=first.sequence_number,
        source_item_ids=first.source_item_ids + second.source_item_ids,
        source_evidence=first.source_evidence + second.source_evidence,
        original_labels=first.original_labels + second.original_labels,
        layout_evidence=first.layout_evidence + second.layout_evidence,
        text=text,
    )
