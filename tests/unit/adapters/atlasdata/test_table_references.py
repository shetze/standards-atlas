"""Table labels are independent of their structural clause coordinates."""

import hashlib

import pytest

from standards_atlas.adapters.atlasdata.domain_mapper import map_atlas_data_to_standard
from standards_atlas.adapters.atlasdata.parser import parse_standard_text
from standards_atlas.adapters.atlasdata.toc_generator import generate_table_structure_records
from standards_atlas.domain.model import Standard


def _standard(structure: str, records: str = "") -> Standard:
    return map_atlas_data_to_standard(
        parse_standard_text(
            'name="Example"\ndigits=8\nstructure=(\n'
            f' "2025 {structure}"\n)\n#---data---#\n{records}'
        ),
        key="EXAMPLE",
    )


@pytest.mark.parametrize(
    ("structure", "reference", "parent"),
    [
        ("1 7.1.2.2 b7.1.2.2.1", "1", "7.1.2.2"),
        ("8.2.18 b8.2.18.5", "5", "8.2.18"),
        ("9:A 9:A.2 b9:A.2.14", "A.14", "A.2"),
        ("9:A 9:A.3 b9:A.3.15", "A.15", "A.3"),
        ("10:B 10:B.3.2.2.6 b10:B.3.2.2.6.5", "B.5", "B.3.2.2.6"),
        ("9:A b9:A.1", "A.1", "A"),
        ("9:A b9:A.0", "A.0", "A"),
        ("0 b5", "5", "0"),
        ("7.1 b7.1.2.2.1", "1", "7.1"),
    ],
)
def test_structure_path_separates_table_label_and_parent(structure, reference, parent):
    document = _standard(structure)

    assert len(document.tables) == 1
    table = document.tables[0]
    assert table.reference == reference
    assert table.parent_clause_reference == parent
    assert table.parent_clause_id == next(
        clause.id for clause in document.clauses if clause.reference.clause == parent
    )
    record = generate_table_structure_records(document)[0]
    assert record.reference == f"Example:2025 Table {reference}"
    assert record.type_marker == parent
    assert record.hash_value == hashlib.md5(f"table|{record.reference}".encode()).hexdigest()


def test_table_numbering_uses_declared_suffix_with_part_and_annex_namespaces():
    document = _standard(
        "1-0 1-7.1 1-b7.1.{1..2} 1-8 1-b8.5 "
        "1-9:A 1-9:A.2 1-b9:A.2.{0..2} 1-9:A.3 1-b9:A.3.15 "
        "1-10:B 1-b10:B.{1..2} 2-0 2-4 2-b4.1 2-9:A 2-b9:A.1"
    )

    assert [table.reference for table in document.tables] == [
        "1",
        "2",
        "5",
        "A.0",
        "A.1",
        "A.2",
        "A.15",
        "B.1",
        "B.2",
        "1",
        "A.1",
    ]
    assert len({table.id for table in document.tables}) == len(document.tables)
    assert [table.sequence_index for table in document.tables] == list(range(11))
    records = generate_table_structure_records(document)
    assert records[0].reference == "Example-1:2025 Table 1"
    assert records[9].reference == "Example-2:2025 Table 1"
    assert records[10].reference == "Example-2:2025 Table A.1"


@pytest.mark.parametrize("record_reference", ["7.1.2.2.1", "1"])
def test_existing_table_and_index_records_bind_to_the_canonical_identity(record_reference):
    document = _standard(
        "1-0 1-7.1.2.2 1-b7.1.2.2.1",
        f"TABLE;old;Example-1:2025 Table {record_reference};Public caption;7.1.2.2\n"
        f"TABLEINDEX;oldindex;Example-1:2025 Table {record_reference};Listed caption;i\n",
    )

    assert len(document.tables) == len(document.table_index) == 1
    table = document.tables[0]
    assert table.reference == "1"
    assert table.title == "Public caption"
    assert table.parent_clause_reference == "7.1.2.2"
    assert table.listed_in_table_index
    assert document.table_index[0].reference == "1"
    assert document.table_index[0].title == "Listed caption"
    assert document.table_index[0].table_id == table.id
    records = generate_table_structure_records(document)
    assert [record.kind for record in records] == ["TABLE", "TABLEINDEX"]
    assert {record.reference for record in records} == {"Example-1:2025 Table 1"}


@pytest.mark.parametrize("canonical_first", [True, False])
def test_legacy_and_canonical_records_merge_without_duplicates(canonical_first):
    canonical = (
        "TABLE;new;Example:2025 Table A.15;Reviewed caption;A.3\n"
        "TABLEINDEX;newindex;Example:2025 Table A.15;Reviewed index caption;i\n"
    )
    legacy = (
        "TABLE;old;Example:2025 Table A.3.15;Old caption;A.3\n"
        "TABLEINDEX;oldindex;Example:2025 Table A.3.15;Old index caption;i\n"
    )
    records = canonical + legacy if canonical_first else legacy + canonical
    document = _standard("9:A 9:A.3 b9:A.3.15", records)

    assert len(document.tables) == len(document.table_index) == 1
    assert document.tables[0].reference == "A.15"
    assert document.tables[0].title == "Reviewed caption"
    assert document.tables[0].parent_clause_reference == "A.3"
    assert document.table_index[0].reference == "A.15"
    assert document.table_index[0].title == "Reviewed index caption"
    assert document.table_index[0].table_id == document.tables[0].id


@pytest.mark.parametrize("canonical_first", [True, False])
def test_empty_canonical_fields_preserve_legacy_metadata(canonical_first):
    canonical = "TABLE;new;Example:2025 Table 1;;\nTABLEINDEX;newindex;Example:2025 Table 1;;i\n"
    legacy = (
        "TABLE;old;Example:2025 Table 7.1.1;Legacy caption;8\n"
        "TABLEINDEX;oldindex;Example:2025 Table 7.1.1;Legacy index caption;i\n"
    )
    records = canonical + legacy if canonical_first else legacy + canonical
    document = _standard("7.1 8 b7.1.1", records)

    assert len(document.tables) == 1
    assert document.tables[0].title == "Legacy caption"
    assert document.tables[0].parent_clause_reference == "8"
    assert document.tables[0].parent_clause_id == document.clauses[1].id
    assert document.table_index[0].title == "Legacy index caption"


def test_table_ids_depend_on_number_and_part_not_the_containing_clause():
    first = _standard("1-7.1 1-b7.1.5")
    moved = _standard("1-8.2 1-b8.2.5")
    other_part = _standard("2-7.1 2-b7.1.5")

    assert first.tables[0].id == moved.tables[0].id
    assert first.tables[0].id != other_part.tables[0].id
    assert first.tables[0].parent_clause_id != moved.tables[0].parent_clause_id


def test_record_aliases_do_not_cross_parts_or_rewrite_undeclared_explicit_labels():
    document = _standard(
        "1-7.1 1-b7.1.1 2-7.1",
        "TABLE;first;Example-1:2025 Table 7.1.1;Declared table;7.1\n"
        "TABLE;second;Example-2:2025 Table 7.1.1;Explicit label;7.1\n"
        "TABLEINDEX;index;Example-2:2025 Table 7.1.1;Explicit label;i\n",
    )

    assert [table.reference for table in document.tables] == ["1", "7.1.1"]
    assert not document.tables[0].listed_in_table_index
    assert document.tables[1].listed_in_table_index
    assert document.table_index[0].reference == "7.1.1"
    records = generate_table_structure_records(document)
    assert [record.reference for record in records] == [
        "Example-1:2025 Table 1",
        "Example-2:2025 Table 7.1.1",
        "Example-2:2025 Table 7.1.1",
    ]


def test_clause_identities_and_source_structure_are_unchanged():
    data = parse_standard_text('name="Example"\ndigits=8\nstructure=(\n "2025 7.1 b7.1.1"\n)\n')
    before = list(data.structure_items)
    document = map_atlas_data_to_standard(data, key="EXAMPLE")
    without_table = _standard("7.1")

    assert data.structure_items == before
    assert data.structure_items[1].visible_reference == "7.1.1"
    assert document.clauses == without_table.clauses


@pytest.mark.parametrize("record_reference", ["7.1.1", "1"])
def test_duplicate_spelling_keeps_existing_last_record_wins_behavior(record_reference):
    document = _standard(
        "7.1 8 b7.1.1",
        f"TABLE;first;Example:2025 Table {record_reference};Earlier caption;8\n"
        f"TABLE;last;Example:2025 Table {record_reference};;\n"
        f"TABLEINDEX;firstindex;Example:2025 Table {record_reference};Earlier list caption;i\n"
        f"TABLEINDEX;lastindex;Example:2025 Table {record_reference};;i\n",
    )

    assert len(document.tables) == len(document.table_index) == 1
    assert document.tables[0].title is None
    assert document.tables[0].parent_clause_reference == "7.1"
    assert document.table_index[0].title is None
