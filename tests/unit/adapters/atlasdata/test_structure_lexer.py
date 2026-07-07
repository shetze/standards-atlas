import pytest

from standards_atlas.adapters.atlasdata.structure_lexer import (
    LexedStructureToken,
    lex_structure_token,
)


def test_lex_plain_token() -> None:
    assert lex_structure_token("r5.1") == LexedStructureToken(
        source="r5.1",
        body="r5.1",
    )


def test_lex_volume_token() -> None:
    assert lex_structure_token("8-r11.4.7.{1..4}") == LexedStructureToken(
        source="8-r11.4.7.{1..4}",
        volume="8",
        body="r11.4.7.{1..4}",
    )


def test_lex_enum_token() -> None:
    assert lex_structure_token("12:C.2.4.{1..4}") == LexedStructureToken(
        source="12:C.2.4.{1..4}",
        enum_prefix="12",
        body="C.2.4.{1..4}",
    )


def test_lex_volume_and_enum_token() -> None:
    assert lex_structure_token("8-12:C.2") == LexedStructureToken(
        source="8-12:C.2",
        volume="8",
        enum_prefix="12",
        body="C.2",
    )


def test_reject_empty_token() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        lex_structure_token("")
