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


def test_reader_reinserts_body_orphaned_heading_by_page_geometry(
    tmp_path: Path,
) -> None:
    import json

    payload = {
        "name": "ORPHANED-ANNEX",
        # Collection order mirrors the problematic IEC 61508-2 extraction:
        # body clauses precede an annex heading omitted from the body tree.
        "texts": [
            {
                "self_ref": "#/texts/1253",
                "label": "section_header",
                "text": "D.1 General",
                "prov": [
                    {
                        "page_no": 76,
                        "bbox": {
                            "l": 70.0,
                            "t": 656.0,
                            "r": 150.0,
                            "b": 645.0,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1255",
                "label": "section_header",
                "text": "D.2 Contents",
                "prov": [
                    {
                        "page_no": 76,
                        "bbox": {
                            "l": 70.0,
                            "t": 562.0,
                            "r": 170.0,
                            "b": 551.0,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1272",
                "label": "section_header",
                "text": "Annex D",
                "prov": [
                    {
                        "page_no": 76,
                        "bbox": {
                            "l": 260.0,
                            "t": 755.0,
                            "r": 340.0,
                            "b": 744.0,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1274",
                "label": "section_header",
                "text": "Safety manual for compliant items",
                "prov": [
                    {
                        "page_no": 76,
                        "bbox": {
                            "l": 180.0,
                            "t": 713.0,
                            "r": 420.0,
                            "b": 702.0,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
        ],
        "body": {
            "children": [
                {"$ref": "#/texts/1253"},
                {"$ref": "#/texts/1255"},
            ]
        },
    }
    source = tmp_path / "orphaned-annex.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    document = DoclingJsonReader().read(source)

    assert [item.id for item in document.items] == [
        "#/texts/1272",
        "#/texts/1274",
        "#/texts/1253",
        "#/texts/1255",
    ]
    assert [item.sequence_number for item in document.items] == list(range(4))


def test_reader_does_not_reorder_body_items_from_geometry(tmp_path: Path) -> None:
    import json

    payload = {
        "name": "DECLARED-ORDER",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "text",
                "text": "First in declared reading order",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 300.0,
                            "t": 500.0,
                            "r": 500.0,
                            "b": 480.0,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "Second in declared reading order",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 70.0,
                            "t": 700.0,
                            "r": 250.0,
                            "b": 680.0,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
        ],
        "body": {
            "children": [
                {"$ref": "#/texts/0"},
                {"$ref": "#/texts/1"},
            ]
        },
    }
    source = tmp_path / "declared-order.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    document = DoclingJsonReader().read(source)

    assert [item.id for item in document.items] == ["#/texts/0", "#/texts/1"]


def test_reader_repairs_complete_but_misordered_annex_heading_block(
    tmp_path: Path,
) -> None:
    import json

    payload = {
        "name": "MISORDERED-ANNEX",
        "texts": [
            {
                "self_ref": "#/texts/1253",
                "label": "section_header",
                "text": "D.1 General",
                "prov": [
                    {
                        "page_no": 76,
                        "bbox": {
                            "l": 70,
                            "t": 665,
                            "r": 150,
                            "b": 655,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1254",
                "label": "text",
                "text": "D.1 body",
                "prov": [
                    {
                        "page_no": 76,
                        "bbox": {
                            "l": 70,
                            "t": 638,
                            "r": 520,
                            "b": 595,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1255",
                "label": "section_header",
                "text": "D.2 Contents",
                "prov": [
                    {
                        "page_no": 76,
                        "bbox": {
                            "l": 70,
                            "t": 572,
                            "r": 160,
                            "b": 562,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1272",
                "label": "section_header",
                "text": "Annex D",
                "prov": [
                    {
                        "page_no": 76,
                        "bbox": {
                            "l": 270,
                            "t": 754,
                            "r": 329,
                            "b": 744,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1273",
                "label": "text",
                "text": "(normative)",
                "prov": [
                    {
                        "page_no": 76,
                        "bbox": {
                            "l": 265,
                            "t": 741,
                            "r": 330,
                            "b": 730,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1274",
                "label": "section_header",
                "text": "Safety manual for compliant items",
                "prov": [
                    {
                        "page_no": 76,
                        "bbox": {
                            "l": 193,
                            "t": 713,
                            "r": 405,
                            "b": 702,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1275",
                "label": "page_footer",
                "text": "footer",
                "prov": [
                    {
                        "page_no": 76,
                        "bbox": {"l": 18, "t": 17, "r": 577, "b": 10, "coord_origin": "BOTTOMLEFT"},
                    }
                ],
            },
        ],
        "body": {
            "children": [
                {"$ref": "#/texts/1253"},
                {"$ref": "#/texts/1254"},
                {"$ref": "#/texts/1255"},
                {"$ref": "#/texts/1272"},
                {"$ref": "#/texts/1273"},
                {"$ref": "#/texts/1274"},
                {"$ref": "#/texts/1275"},
            ]
        },
    }
    source = tmp_path / "misordered-annex.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    document = DoclingJsonReader().read(source)

    assert [item.id for item in document.items] == [
        "#/texts/1272",
        "#/texts/1273",
        "#/texts/1274",
        "#/texts/1253",
        "#/texts/1254",
        "#/texts/1255",
        "#/texts/1275",
    ]
    assert [item.sequence_number for item in document.items] == list(range(7))


def test_reader_does_not_move_annex_heading_without_preceding_child_clause(
    tmp_path: Path,
) -> None:
    import json

    payload = {
        "name": "CORRECT-ANNEX",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "Annex D",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 270,
                            "t": 754,
                            "r": 329,
                            "b": 744,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1",
                "label": "section_header",
                "text": "D.1 General",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 70,
                            "t": 665,
                            "r": 150,
                            "b": 655,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
        ],
        "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/texts/1"}]},
    }
    source = tmp_path / "correct-annex.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    document = DoclingJsonReader().read(source)

    assert [item.id for item in document.items] == ["#/texts/0", "#/texts/1"]


def test_reader_repairs_misordered_numbered_clause_heading(tmp_path: Path) -> None:
    import json

    payload = {
        "name": "MISORDERED-CLAUSE",
        "texts": [
            {
                "self_ref": "#/texts/2377",
                "label": "section_header",
                "text": "D.2.1.2 Results",
                "prov": [
                    {
                        "page_no": 110,
                        "bbox": {
                            "l": 70,
                            "t": 590,
                            "r": 170,
                            "b": 581,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/2379",
                "label": "formula",
                "text": "formula",
                "prov": [
                    {
                        "page_no": 110,
                        "bbox": {
                            "l": 221,
                            "t": 548,
                            "r": 410,
                            "b": 521,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/2381",
                "label": "text",
                "text": "Example result text",
                "prov": [
                    {
                        "page_no": 110,
                        "bbox": {
                            "l": 70,
                            "t": 360,
                            "r": 527,
                            "b": 328,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/2382",
                "label": "section_header",
                "text": "D.2.2 Testing of an input space",
                "prov": [
                    {
                        "page_no": 110,
                        "bbox": {
                            "l": 70,
                            "t": 311,
                            "r": 487,
                            "b": 302,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/2385",
                "label": "section_header",
                "text": "D.2.2.2 Results",
                "prov": [
                    {
                        "page_no": 110,
                        "bbox": {
                            "l": 70,
                            "t": 230,
                            "r": 169,
                            "b": 221,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/2387",
                "label": "section_header",
                "text": "D.2.1.3 Example",
                "prov": [
                    {
                        "page_no": 110,
                        "bbox": {
                            "l": 70,
                            "t": 480,
                            "r": 174,
                            "b": 472,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
        ],
        "tables": [
            {
                "self_ref": "#/tables/9",
                "label": "table",
                "data": {"table_cells": [], "num_rows": 0, "num_cols": 0},
                "prov": [
                    {
                        "page_no": 110,
                        "bbox": {
                            "l": 240,
                            "t": 429,
                            "r": 355,
                            "b": 379,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            }
        ],
        "body": {
            "children": [
                {"$ref": "#/texts/2377"},
                {"$ref": "#/texts/2379"},
                {"$ref": "#/tables/9"},
                {"$ref": "#/texts/2381"},
                {"$ref": "#/texts/2382"},
                {"$ref": "#/texts/2385"},
                {"$ref": "#/texts/2387"},
            ]
        },
    }
    source = tmp_path / "misordered-clause.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    document = DoclingJsonReader().read(source)

    assert [item.id for item in document.items] == [
        "#/texts/2377",
        "#/texts/2379",
        "#/texts/2387",
        "#/tables/9",
        "#/texts/2381",
        "#/texts/2382",
        "#/texts/2385",
    ]


def test_reader_does_not_reorder_reference_without_geometric_confirmation(
    tmp_path: Path,
) -> None:
    import json

    payload = {
        "name": "NO-GEOMETRIC-CONFIRMATION",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "D.2.2 Results",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 70,
                            "t": 500,
                            "r": 170,
                            "b": 490,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/1",
                "label": "section_header",
                "text": "D.2.1.3 Example",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 70,
                            "t": 400,
                            "r": 170,
                            "b": 390,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
        ],
        "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/texts/1"}]},
    }
    source = tmp_path / "no-geometric-confirmation.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    document = DoclingJsonReader().read(source)

    assert [item.id for item in document.items] == ["#/texts/0", "#/texts/1"]
