from pytest import raises

from standards_atlas.adapters.doorstop.doorstop_id_generator import (
    DoorstopIdGenerationContext,
    generate_doorstop_num_id,
)


def test_generate_simple_clause_id() -> None:
    assert generate_doorstop_num_id(
        visible_reference="5.1.2",
        context=DoorstopIdGenerationContext(digits=8),
    ) == "05010200"


def test_generate_requirement_id() -> None:
    assert generate_doorstop_num_id(
        visible_reference="5.1.2.1",
        context=DoorstopIdGenerationContext(digits=8),
    ) == "05010201"


def test_generate_volume_prefixed_id() -> None:
    assert generate_doorstop_num_id(
        visible_reference="11.4.7.1",
        volume="8",
        context=DoorstopIdGenerationContext(
            digits=10,
            part_digits=2,
        ),
    ) == "0811040701"


def test_generate_volume_with_part_shift() -> None:
    assert generate_doorstop_num_id(
        visible_reference="1.2",
        volume="3",
        context=DoorstopIdGenerationContext(
            digits=8,
            part_shift=10,
            part_digits=2,
        ),
    ) == "13010200"


def test_generate_annex_id_from_enum_prefix() -> None:
    assert generate_doorstop_num_id(
        visible_reference="A",
        enum_prefix="10",
        context=DoorstopIdGenerationContext(digits=8),
    ) == "10000000"


def test_generate_nested_annex_id_from_enum_prefix() -> None:
    assert generate_doorstop_num_id(
        visible_reference="C.2.4.1",
        enum_prefix="12",
        context=DoorstopIdGenerationContext(digits=8),
    ) == "12020401"


def test_generate_three_digit_last_segment() -> None:
    assert generate_doorstop_num_id(
        visible_reference="4.133",
        volume="0",
        identifier_width=3,
        context=DoorstopIdGenerationContext(
            digits=8,
            part_digits=1,
        ),
    ) == "00413300"


def test_reject_non_numeric_segment_without_enum_prefix() -> None:
    with raises(ValueError, match="Reference segment must be numeric"):
        generate_doorstop_num_id(
            visible_reference="A.1",
            context=DoorstopIdGenerationContext(digits=8),
        )


def test_reject_id_exceeding_configured_width() -> None:
    with raises(ValueError, match="exceeds configured width"):
        generate_doorstop_num_id(
            visible_reference="11.22.33.44.55",
            context=DoorstopIdGenerationContext(digits=8),
        )
