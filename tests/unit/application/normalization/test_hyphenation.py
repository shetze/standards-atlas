from standards_atlas.application.model.normalized_document import (
    NormalizationOptions,
    NormalizedText,
    TransformationEvent,
)
from standards_atlas.application.normalization.hyphenation import repair_hyphenation


def _event_factory(**values: object) -> TransformationEvent:
    return TransformationEvent(id="tx:0000000000000000", **values)


def test_repairs_cross_item_lowercase_hyphenation() -> None:
    items = [
        NormalizedText(id="one", sequence_number=0, source_item_ids=("one",), text="require-"),
        NormalizedText(id="two", sequence_number=1, source_item_ids=("two",), text="ment"),
    ]

    normalized, count, events = repair_hyphenation(
        items,
        NormalizationOptions(),
        _event_factory,
    )

    assert count == 1
    assert [item.text for item in normalized] == ["requirement"]
    assert normalized[0].source_item_ids == ("one", "two")
    assert len(events) == 1
