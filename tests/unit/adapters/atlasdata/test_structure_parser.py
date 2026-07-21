import pytest

from standards_atlas.adapters.atlasdata.structure_ast import StructureRange, StructureToken
from standards_atlas.adapters.atlasdata.structure_lexer import LexedStructureToken
from standards_atlas.adapters.atlasdata.structure_parser import parse_lexed_structure_token
from standards_atlas.adapters.atlasdata.structure_types import AtlasItemType


def test_parse_requirement_token() -> None:
    parsed = parse_lexed_structure_token(
        LexedStructureToken(
            source="r5.1.{1..3}",
            body="r5.1.{1..3}",
        )
    )

    assert parsed == StructureToken(
        source="r5.1.{1..3}",
        reference_template="5.1.{1..3}",
        item_type=AtlasItemType.REQUIREMENT,
        ranges=(StructureRange(start=1, end=3),),
    )


def test_parse_three_digit_marker() -> None:
    parsed = parse_lexed_structure_token(
        LexedStructureToken(
            source="0-4.+{1..133}",
            body="4.+{1..133}",
            volume="0",
        )
    )

    assert parsed.identifier_width == 3
    assert parsed.reference_template == "4.{1..133}"


def test_parse_canonical_typed_enum_token() -> None:
    parsed = parse_lexed_structure_token(
        LexedStructureToken(
            source="r12:C.2.4.{1..4}",
            body="r12:C.2.4.{1..4}",
        )
    )

    assert parsed.enum_prefix == "12"
    assert parsed.reference_template == "C.2.4.{1..4}"
    assert parsed.item_type == AtlasItemType.REQUIREMENT


def test_parse_canonical_untyped_enum_token() -> None:
    parsed = parse_lexed_structure_token(
        LexedStructureToken(
            source="12:C.2.4.{1..4}",
            body="12:C.2.4.{1..4}",
        )
    )

    assert parsed.enum_prefix == "12"
    assert parsed.reference_template == "C.2.4.{1..4}"
    assert parsed.item_type == AtlasItemType.TOC


def test_parse_compatibility_typed_enum_token() -> None:
    parsed = parse_lexed_structure_token(
        LexedStructureToken(
            source="12:rC.2.4.{1..4}",
            body="12:rC.2.4.{1..4}",
        )
    )

    assert parsed.enum_prefix == "12"
    assert parsed.reference_template == "C.2.4.{1..4}"
    assert parsed.item_type == AtlasItemType.REQUIREMENT


def test_reject_invalid_canonical_enum_prefix() -> None:
    with pytest.raises(ValueError, match="Invalid enum prefix"):
        parse_lexed_structure_token(LexedStructureToken(source="rX:C", body="rX:C"))


def test_reject_descending_range() -> None:
    with pytest.raises(ValueError, match="descending range"):
        parse_lexed_structure_token(
            LexedStructureToken(
                source="r5.{3..1}",
                body="r5.{3..1}",
            )
        )
