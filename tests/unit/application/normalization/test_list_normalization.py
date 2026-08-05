from standards_atlas.application.model.normalized_document import (
    NormalizationOptions,
    NormalizedText,
    TransformationEvent,
)
from standards_atlas.application.normalization.list_normalization import (
    marker_is_ordered,
    normalize_list_marker,
    normalize_lists,
)


def _event_factory(**values: object) -> TransformationEvent:
    return TransformationEvent(id="tx:0000000000000000", **values)


def test_normalize_list_marker_and_ordering() -> None:
    assert normalize_list_marker(" 1. ") == "1"
    assert marker_is_ordered("1.") is True
    assert marker_is_ordered("-") is False


def test_detects_consecutive_marked_text_items() -> None:
    items = [
        NormalizedText(id="one", sequence_number=0, source_item_ids=("one",), text="a) first"),
        NormalizedText(id="two", sequence_number=1, source_item_ids=("two",), text="b) second"),
    ]
    normalized, count, events = normalize_lists(items, NormalizationOptions(), _event_factory)
    assert count == 1
    assert len(normalized) == 1
    assert normalized[0].type == "list"
    assert len(events) == 1
