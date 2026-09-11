"""TABLE wire columns are generated parent first, human-reviewed caption last."""

import pytest

from standards_atlas.adapters.atlasdata.parser import (
    TABLE_RECORD_LAYOUT,
    InitializationRecord,
    parse_initialization_records,
    render_initialization_record,
    render_initialization_records,
)


@pytest.mark.parametrize(
    ("fields", "parent", "caption"),
    [
        ("7.1.2.2;Reviewed caption", "7.1.2.2", "Reviewed caption"),
        ("Reviewed caption;7.1.2.2", "7.1.2.2", "Reviewed caption"),
        ("7.1.2.2;", "7.1.2.2", ""),
        (";7.1.2.2", "7.1.2.2", ""),
        ("A.2;Grenzwerte", "A.2", "Grenzwerte"),
        ("Grenzwerte;A.2", "A.2", "Grenzwerte"),
        ("A;", "A", ""),
        (";A", "A", ""),
        ("0;Overview", "0", "Overview"),
        ("Overview;0", "0", "Overview"),
        (";Unassigned caption", "", "Unassigned caption"),
        ("Unassigned caption;", "", "Unassigned caption"),
        (";", "", ""),
    ],
)
def test_unmarked_table_layouts_import_with_the_same_semantics(fields, parent, caption):
    record = parse_initialization_records(
        f"#---data---#\nTABLE;stable;Example:2025 Table 1;{fields}\n"
    )[0]

    assert record.hash_value == "stable"
    assert record.type_marker == parent
    assert record.content == caption
    assert render_initialization_record(record) == (
        f"TABLE;stable;Example:2025 Table 1;{parent};{caption}"
    )


@pytest.mark.parametrize("caption", ["", "A", "A.2", "1", "7.1", "Overview"])
@pytest.mark.parametrize("parent", ["", "7.1", "A.2"])
def test_explicit_layout_preserves_reference_shaped_captions_and_empty_parents(parent, caption):
    record = InitializationRecord(
        kind="TABLE",
        hash_value="stable",
        reference="Example:2025 Table 1",
        content=caption,
        type_marker=parent,
    )
    body = render_initialization_records([record])

    assert body.splitlines()[0] == TABLE_RECORD_LAYOUT
    assert body.splitlines()[1].split(";")[3:] == [parent, caption]
    assert parse_initialization_records(f"#---data---#\n{body}\n") == [record]


@pytest.mark.parametrize("fields", ["7.1;A.2", "Caption;Other caption"])
def test_ambiguous_unmarked_populated_fields_require_an_explicit_layout(fields):
    with pytest.raises(ValueError, match="Ambiguous TABLE field order"):
        parse_initialization_records(f"#---data---#\nTABLE;h;Example Table 1;{fields}\n")


def test_explicit_legacy_layout_can_migrate_a_numeric_caption_without_parent():
    text = "#---data---#\n# table-record-layout: caption-parent\nTABLE;h;Example Table 1;7.1;\n"
    record = parse_initialization_records(text)[0]
    assert record.content == "7.1"
    assert record.type_marker == ""
    canonical = render_initialization_records([record])
    assert canonical.endswith("TABLE;h;Example Table 1;;7.1")
    assert parse_initialization_records(f"#---data---#\n{canonical}\n") == [record]


@pytest.mark.parametrize(
    "layout",
    [
        "# table-record-layout: invalid",
        "# table-record-layout: parent-caption\n# table-record-layout: caption-parent",
    ],
)
def test_invalid_or_conflicting_layouts_are_not_silently_reinterpreted(layout):
    with pytest.raises(ValueError, match="Invalid or conflicting table-record-layout"):
        parse_initialization_records(f"#---data---#\n{layout}\nTABLE;h;Example Table 1;A;\n")


@pytest.mark.parametrize("kind", ["TOC", "PublicTXT", "LocalTXT", "TEXT", "TABLEINDEX"])
def test_non_table_columns_and_semantic_tags_remain_unchanged(kind):
    marker = "i" if kind == "TABLEINDEX" else "u"
    line = f"{kind};hash;Example:2025 1;Public content;{marker};SP-DES,KK-CNC"
    record = parse_initialization_records(f"#---data---#\n{line}\n")[0]

    assert record.content == "Public content"
    assert record.type_marker == marker
    assert record.semantic_tags == ("SP-DES", "KK-CNC")
    assert render_initialization_records([record]) == line


def test_optional_table_semantic_tags_survive_the_field_swap():
    record = parse_initialization_records(
        "#---data---#\nTABLE;h;Example Table 1;Reviewed caption;A.2;KK-CNC\n"
    )[0]
    body = render_initialization_records([record])
    assert body.endswith("TABLE;h;Example Table 1;A.2;Reviewed caption;KK-CNC")
    assert parse_initialization_records(f"#---data---#\n{body}") == [record]


def test_empty_data_section_stays_empty():
    assert render_initialization_records([]) == ""
