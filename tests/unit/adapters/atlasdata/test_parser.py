from standards_atlas.adapters.atlasdata.metadata import AtlasMetadata
from standards_atlas.adapters.atlasdata.parser import (
    AtlasStandardData,
    InitializationRecord,
    parse_initialization_records,
    parse_standard_text,
    parse_structure_block,
)
from standards_atlas.adapters.atlasdata.structure_expander import AtlasItemType


def test_parse_structure_block() -> None:
    text = """
name="Example"
digits=4

structure=(
 "1 2 3"
 "r5.1.{1..2}"
)
"""

    assert parse_structure_block(text) == [
        "1 2 3",
        "r5.1.{1..2}",
    ]


def test_parse_initialization_records() -> None:
    text = """
#---data---#
TOC;abc;EN 50716:2023 1;Scope;u
TEXT;def;EN 50716:2023 1.1;Some text;s
"""

    assert parse_initialization_records(text) == [
        InitializationRecord(
            kind="TOC",
            hash_value="abc",
            reference="EN 50716:2023 1",
            content="Scope",
            type_marker="u",
        ),
        InitializationRecord(
            kind="TEXT",
            hash_value="def",
            reference="EN 50716:2023 1.1",
            content="Some text",
            type_marker="s",
        ),
    ]


def test_parse_standard_text() -> None:
    text = """
parent="IEC61508"
digits=8
partShift=0
partDigits=2
name="EN 50716"
oyr=2023

structure=(
 "1 s1.{1..2} r5.1.{1..2}"
)

#---data---#
TOC;abc;EN 50716:2023 1;Scope;u
TEXT;def;EN 50716:2023 1.1;Some text;s
"""

    parsed = parse_standard_text(text)

    assert parsed == AtlasStandardData(
        metadata=AtlasMetadata(
            name="EN 50716",
            digits=8,
            parent="IEC61508",
            part_shift=0,
            part_digits=2,
            official_year=2023,
        ),
        structure_items=parsed.structure_items,
        initialization_records=[
            InitializationRecord(
                kind="TOC",
                hash_value="abc",
                reference="EN 50716:2023 1",
                content="Scope",
                type_marker="u",
            ),
            InitializationRecord(
                kind="TEXT",
                hash_value="def",
                reference="EN 50716:2023 1.1",
                content="Some text",
                type_marker="s",
            ),
        ],
    )

    assert [item.visible_reference for item in parsed.structure_items] == [
        "1",
        "1.1",
        "1.2",
        "5.1.1",
        "5.1.2",
    ]

    assert [item.item_type for item in parsed.structure_items] == [
        AtlasItemType.TOC,
        AtlasItemType.SCOPE,
        AtlasItemType.SCOPE,
        AtlasItemType.REQUIREMENT,
        AtlasItemType.REQUIREMENT,
    ]


def test_parse_without_data_section() -> None:
    text = """
name="Example"
digits=4

structure=(
 "1 2 3"
)
"""

    parsed = parse_standard_text(text)

    assert parsed.initialization_records == []
