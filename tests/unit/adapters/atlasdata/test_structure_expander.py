import pytest

from standards_atlas.adapters.atlasdata.structure_expander import (
    StructureItem,
    expand_structure_line,
    expand_structure_token,
)
from standards_atlas.adapters.atlasdata.structure_types import AtlasItemType


def test_expand_plain_toc_token() -> None:
    assert expand_structure_token("1") == [
        StructureItem(
            visible_reference="1",
            item_type=AtlasItemType.TOC,
            source_token="1",
        )
    ]


def test_expand_requirement_range() -> None:
    items = expand_structure_token("r5.1.2.{1..3}")

    assert [item.visible_reference for item in items] == [
        "5.1.2.1",
        "5.1.2.2",
        "5.1.2.3",
    ]
    assert all(item.item_type == AtlasItemType.REQUIREMENT for item in items)


def test_expand_term_range() -> None:
    items = expand_structure_token("t3.1.{1..2}")

    assert [item.visible_reference for item in items] == [
        "3.1.1",
        "3.1.2",
    ]
    assert all(item.item_type == AtlasItemType.TERM for item in items)


def test_expand_enum_prefix() -> None:
    assert expand_structure_token("10:A") == [
        StructureItem(
            visible_reference="A",
            item_type=AtlasItemType.TOC,
            enum_prefix="10",
            source_token="10:A",
        )
    ]


def test_expand_enum_prefix_with_nested_range() -> None:
    items = expand_structure_token("12:C.2.4.{1..2}")

    assert [item.visible_reference for item in items] == [
        "C.2.4.1",
        "C.2.4.2",
    ]
    assert all(item.enum_prefix == "12" for item in items)


def test_expand_volume_requirement_range() -> None:
    items = expand_structure_token("8-r11.4.7.{1..2}")

    assert [item.visible_reference for item in items] == [
        "11.4.7.1",
        "11.4.7.2",
    ]
    assert all(item.volume == "8" for item in items)
    assert all(item.item_type == AtlasItemType.REQUIREMENT for item in items)


def test_expand_three_digit_identifier_marker() -> None:
    items = expand_structure_token("0-4.+{1..2}")

    assert [item.visible_reference for item in items] == [
        "4.1",
        "4.2",
    ]
    assert all(item.volume == "0" for item in items)
    assert all(item.identifier_width == 3 for item in items)


def test_expand_structure_line() -> None:
    items = expand_structure_line("1 s1.{1..2} r5.1.{1..2}")

    assert [item.visible_reference for item in items] == [
        "1",
        "1.1",
        "1.2",
        "5.1.1",
        "5.1.2",
    ]

    assert [item.item_type for item in items] == [
        AtlasItemType.TOC,
        AtlasItemType.SCOPE,
        AtlasItemType.SCOPE,
        AtlasItemType.REQUIREMENT,
        AtlasItemType.REQUIREMENT,
    ]


def test_reject_empty_token() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        expand_structure_token("")


def test_reject_descending_range() -> None:
    with pytest.raises(ValueError, match="descending range"):
        expand_structure_token("r5.{3..1}")


def test_reject_missing_reference_after_type_prefix() -> None:
    with pytest.raises(ValueError, match="missing a reference"):
        expand_structure_token("r")


def test_structure_line_uses_leading_year_as_publication_year() -> None:
    items = expand_structure_line("2010 1 r5.1.{1..2}")

    assert [item.visible_reference for item in items] == [
        "1",
        "5.1.1",
        "5.1.2",
    ]

    assert all(item.publication_year == 2010 for item in items)


def test_leading_year_token_is_not_expanded_as_structure_item() -> None:
    items = expand_structure_line("2023 1 2 3")

    assert [item.visible_reference for item in items] == [
        "1",
        "2",
        "3",
    ]
