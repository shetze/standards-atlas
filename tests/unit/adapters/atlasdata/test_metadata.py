import pytest

from standards_atlas.adapters.atlasdata.metadata import AtlasMetadata, parse_metadata


def test_parse_required_metadata() -> None:
    text = """
name="EN 50716"
digits=8

structure=(
 "1 2 3"
)
"""

    assert parse_metadata(text) == AtlasMetadata(
        name="EN 50716",
        digits=8,
    )


def test_parse_full_metadata() -> None:
    text = """
parent="IEC61508"
digits=8
partShift=0
partDigits=2
name="EN 50716"
oyr=2023

structure=(
 "1 2 3"
)
"""

    assert parse_metadata(text) == AtlasMetadata(
        name="EN 50716",
        digits=8,
        parent="IEC61508",
        part_shift=0,
        part_digits=2,
        official_year=2023,
    )


def test_preserve_unknown_metadata_fields() -> None:
    text = """
name="Example"
digits=4
legacyMode="true"

structure=(
 "1 2 3"
)
"""

    metadata = parse_metadata(text)

    assert metadata.extra_fields == {
        "legacyMode": "true",
    }


def test_stop_parsing_at_structure_block() -> None:
    text = """
name="Example"
digits=4

structure=(
 "1 2 3"
)

name="Should Not Be Parsed"
digits=999
"""

    metadata = parse_metadata(text)

    assert metadata.name == "Example"
    assert metadata.digits == 4


def test_reject_missing_name() -> None:
    text = """
digits=4

structure=(
 "1 2 3"
)
"""

    with pytest.raises(ValueError, match="Missing required metadata field"):
        parse_metadata(text)


def test_reject_missing_digits() -> None:
    text = """
name="Example"

structure=(
 "1 2 3"
)
"""

    with pytest.raises(ValueError, match="Missing required metadata field"):
        parse_metadata(text)


def test_reject_non_integer_digits() -> None:
    text = """
name="Example"
digits=abc

structure=(
 "1 2 3"
)
"""

    with pytest.raises(ValueError, match="must be an integer"):
        parse_metadata(text)
