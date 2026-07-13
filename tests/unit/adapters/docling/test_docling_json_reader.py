from pathlib import Path

from standards_atlas.adapters.docling import DoclingJsonReader
from standards_atlas.application.model import (
    ExtractedHeading,
    ExtractedList,
    ExtractedPicture,
    ExtractedTable,
    ExtractedText,
)

FIXTURE = Path("tests/fixtures/docling/minimal-standard.json")


def test_reader_maps_native_docling_json_in_reading_order() -> None:
    document = DoclingJsonReader().read(FIXTURE)

    assert document.source_id == "MIN-STD"
    assert [type(item) for item in document.items] == [
        ExtractedHeading,
        ExtractedText,
        ExtractedList,
        ExtractedTable,
        ExtractedPicture,
    ]
    assert [item.sequence_number for item in document.items] == list(range(5))


def test_reader_preserves_provenance_and_table_structure() -> None:
    document = DoclingJsonReader().read(FIXTURE)
    heading = document.items[0]
    table = document.items[3]

    assert heading.source_evidence[0].page_number == 1
    assert heading.source_evidence[0].locator == "#/texts/0"
    assert heading.source_evidence[0].bounding_box is not None
    assert table.rows[0].cells[0].text == "Name"
    assert table.rows[0].cells[0].is_header is True
    assert table.rows[1].cells[1].text == "1"


def test_reader_groups_consecutive_docling_list_items() -> None:
    document = DoclingJsonReader().read(FIXTURE)
    extracted_list = document.items[2]

    assert isinstance(extracted_list, ExtractedList)
    assert [item.text for item in extracted_list.items] == ["first item", "second item"]


def test_reader_preserves_unknown_docling_items(tmp_path: Path) -> None:
    payload = {
        "name": "UNKNOWN",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "custom_standard_element",
                "text": "Content that must not be lost",
                "prov": [{"page_no": 2}],
            }
        ],
        "body": {"children": [{"$ref": "#/texts/0"}]},
    }
    source = tmp_path / "unknown.json"
    import json

    source.write_text(json.dumps(payload), encoding="utf-8")

    document = DoclingJsonReader().read(source)
    item = document.items[0]

    assert item.type == "unknown"
    assert item.original_label == "custom_standard_element"
    assert item.text == "Content that must not be lost"


def test_reader_rejects_corrupt_json(tmp_path: Path) -> None:
    import pytest

    from standards_atlas.adapters.docling import DoclingDocumentValidationError

    source = tmp_path / "corrupt.json"
    source.write_text("{", encoding="utf-8")

    with pytest.raises(DoclingDocumentValidationError):
        DoclingJsonReader().read(source)
