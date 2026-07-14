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


def test_reader_preserves_individual_list_item_source_ids() -> None:
    document = DoclingJsonReader().read(FIXTURE)
    extracted_list = document.items[2]

    assert isinstance(extracted_list, ExtractedList)
    assert [item.id for item in extracted_list.items] == ["#/texts/2", "#/texts/3"]
    assert [item.source_evidence[0].locator for item in extracted_list.items] == [
        "#/texts/2",
        "#/texts/3",
    ]


def test_reader_promotes_clause_like_list_items_without_reordering(tmp_path: Path) -> None:
    import json

    payload = {
        "name": "CLAUSE-LIST",
        "texts": [
            {
                "self_ref": "#/texts/562",
                "label": "list_item",
                "marker": "4.1",
                "text": "First clause",
                "prov": [{"page_no": 21}],
            },
            {
                "self_ref": "#/texts/563",
                "label": "text",
                "text": "Text between clauses.",
                "prov": [{"page_no": 21}],
            },
            {
                "self_ref": "#/texts/578",
                "label": "list_item",
                "marker": "4.4",
                "text": "Fourth clause",
                "prov": [{"page_no": 21}],
            },
            {
                "self_ref": "#/texts/579",
                "label": "list_item",
                "marker": "4.5",
                "text": "Fifth clause",
                "prov": [{"page_no": 21}],
            },
            {
                "self_ref": "#/texts/580",
                "label": "text",
                "text": "Following text.",
                "prov": [{"page_no": 21}],
            },
        ],
        "body": {
            "children": [
                {"$ref": "#/texts/562"},
                {"$ref": "#/texts/563"},
                {"$ref": "#/texts/578"},
                {"$ref": "#/texts/579"},
                {"$ref": "#/texts/580"},
            ]
        },
    }
    source = tmp_path / "clause-list.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    document = DoclingJsonReader().read(source)

    assert [item.id for item in document.items] == [
        "#/texts/562",
        "#/texts/563",
        "#/texts/578",
        "#/texts/579",
        "#/texts/580",
    ]
    assert [item.sequence_number for item in document.items] == list(range(5))
    assert [item.type for item in document.items] == [
        "text",
        "text",
        "text",
        "text",
        "text",
    ]
    assert [item.text for item in document.items] == [
        "4.1 First clause",
        "Text between clauses.",
        "4.4 Fourth clause",
        "4.5 Fifth clause",
        "Following text.",
    ]


def test_reader_keeps_real_list_items_grouped_with_original_positions(
    tmp_path: Path,
) -> None:
    import json

    payload = {
        "name": "REAL-LIST",
        "texts": [
            {
                "self_ref": "#/texts/10",
                "label": "list_item",
                "marker": "—",
                "text": "First",
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/11",
                "label": "list_item",
                "marker": "—",
                "text": "Second",
                "prov": [{"page_no": 1}],
            },
        ],
        "body": {
            "children": [
                {"$ref": "#/texts/10"},
                {"$ref": "#/texts/11"},
            ]
        },
    }
    source = tmp_path / "real-list.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    document = DoclingJsonReader().read(source)
    extracted_list = document.items[0]

    assert isinstance(extracted_list, ExtractedList)
    assert [entry.sequence_number for entry in extracted_list.items] == [0, 1]
    assert [entry.id for entry in extracted_list.items] == ["#/texts/10", "#/texts/11"]


def test_reader_resolves_group_references_in_body_order(tmp_path: Path) -> None:
    import json

    payload = {
        "name": "GROUP-ORDER",
        # Deliberately store texts in an order which does not match reading order.
        "texts": [
            {
                "self_ref": "#/texts/579",
                "label": "list_item",
                "marker": "4.5",
                "text": "Fifth clause",
                "prov": [{"page_no": 21}],
            },
            {
                "self_ref": "#/texts/562",
                "label": "list_item",
                "marker": "4.1",
                "text": "First clause",
                "prov": [{"page_no": 21}],
            },
            {
                "self_ref": "#/texts/578",
                "label": "list_item",
                "marker": "4.4",
                "text": "Fourth clause",
                "prov": [{"page_no": 21}],
            },
        ],
        "groups": [
            {
                "self_ref": "#/groups/0",
                "label": "list",
                "children": [
                    {"$ref": "#/texts/562"},
                    {"$ref": "#/texts/578"},
                    {"$ref": "#/texts/579"},
                ],
            }
        ],
        "body": {"children": [{"$ref": "#/groups/0"}]},
    }
    source = tmp_path / "group-order.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    document = DoclingJsonReader().read(source)

    assert [item.id for item in document.items] == [
        "#/texts/562",
        "#/texts/578",
        "#/texts/579",
    ]
    assert [item.text for item in document.items] == [
        "4.1 First clause",
        "4.4 Fourth clause",
        "4.5 Fifth clause",
    ]


def test_reader_does_not_emit_group_nodes_as_unknown_items(tmp_path: Path) -> None:
    import json

    payload = {
        "name": "GROUPS",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "text",
                "text": "Content",
                "prov": [{"page_no": 1}],
            }
        ],
        "groups": [
            {
                "self_ref": "#/groups/0",
                "label": "group",
                "children": [{"$ref": "#/texts/0"}],
            }
        ],
        "body": {"children": [{"$ref": "#/groups/0"}]},
    }
    source = tmp_path / "groups.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    document = DoclingJsonReader().read(source)

    assert len(document.items) == 1
    assert document.items[0].id == "#/texts/0"
