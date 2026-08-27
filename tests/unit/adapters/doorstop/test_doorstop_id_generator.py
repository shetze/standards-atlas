from pytest import raises

from standards_atlas.adapters.doorstop.id_generator import (
    DoorstopIdContext,
    generate_doorstop_id,
    generate_doorstop_level,
)


def test_generate_simple_clause_id() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="5.1.2",
            context=DoorstopIdContext(digits=8),
        )
        == "05010200"
    )


def test_generate_requirement_id() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="5.1.2.1",
            context=DoorstopIdContext(digits=8),
        )
        == "05010201"
    )


def test_generate_volume_prefixed_id() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="11.4.7.1",
            volume="8",
            context=DoorstopIdContext(
                digits=10,
                part_digits=2,
            ),
        )
        == "0811040701"
    )


def test_generate_volume_with_part_shift() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="1.2",
            volume="3",
            context=DoorstopIdContext(
                digits=8,
                part_shift=10,
                part_digits=2,
            ),
        )
        == "13010200"
    )


def test_generate_supplement_volume_id() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="4.1",
            volume="3§1",
            context=DoorstopIdContext(
                digits=12,
                part_shift=1,
            ),
        )
        == "040104010000"
    )


def test_supplement_volume_does_not_collide_with_numeric_part() -> None:
    context = DoorstopIdContext(digits=12, part_shift=1)

    supplement_id = generate_doorstop_id(
        visible_reference="4.1",
        volume="3§1",
        context=context,
    )
    numeric_part_id = generate_doorstop_id(
        visible_reference="4.1",
        volume="31",
        context=context,
    )

    assert supplement_id != numeric_part_id


def test_reject_non_numeric_supplement_volume() -> None:
    with raises(ValueError, match="Supplement must be numeric"):
        generate_doorstop_id(
            visible_reference="4.1",
            volume="3§draft",
            context=DoorstopIdContext(digits=12),
        )


def test_generate_annex_id_from_enum_prefix() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="A",
            enum_prefix="10",
            context=DoorstopIdContext(digits=8),
        )
        == "10000000"
    )


def test_generate_nested_annex_id_from_enum_prefix() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="C.2.4.1",
            enum_prefix="12",
            context=DoorstopIdContext(digits=8),
        )
        == "12020401"
    )


def test_generate_three_digit_last_segment() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="4.133",
            volume="0",
            identifier_width=3,
            context=DoorstopIdContext(
                digits=8,
                part_digits=1,
            ),
        )
        == "00413300"
    )


def test_generate_standalone_annex_id() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="A",
            context=DoorstopIdContext(digits=8),
        )
        == "10000000"
    )


def test_generate_nested_annex_id_without_explicit_enum_prefix() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="A.1",
            context=DoorstopIdContext(digits=8),
        )
        == "10010000"
    )


def test_generate_annex_c_id_without_explicit_enum_prefix() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="C.2.4.1",
            context=DoorstopIdContext(digits=8),
        )
        == "12020401"
    )


def test_explicit_enum_prefix_overrides_annex_mapping() -> None:
    assert (
        generate_doorstop_id(
            visible_reference="A.1",
            enum_prefix="20",
            context=DoorstopIdContext(digits=8),
        )
        == "20010000"
    )


def test_reject_id_exceeding_configured_width() -> None:
    with raises(ValueError, match="exceeds configured width"):
        generate_doorstop_id(
            visible_reference="11.22.33.44.55",
            context=DoorstopIdContext(digits=8),
        )


def test_generate_numeric_doorstop_level() -> None:
    assert (
        generate_doorstop_level(
            visible_reference="5.1.2",
        )
        == "5.1.2"
    )


def test_generate_standalone_annex_level() -> None:
    assert (
        generate_doorstop_level(
            visible_reference="A",
        )
        == "10"
    )


def test_generate_nested_annex_level() -> None:
    assert (
        generate_doorstop_level(
            visible_reference="A.1.2",
        )
        == "10.1.2"
    )


def test_generate_annex_c_level() -> None:
    assert (
        generate_doorstop_level(
            visible_reference="C.2.4",
        )
        == "12.2.4"
    )


def test_explicit_enum_prefix_overrides_annex_level_mapping() -> None:
    assert (
        generate_doorstop_level(
            visible_reference="A.1",
            enum_prefix="20",
        )
        == "20.1"
    )


def test_fixed_volume_depth_pads_primary_part_namespace() -> None:
    context = DoorstopIdContext(digits=12, volume_depth=2)

    primary_id = generate_doorstop_id(
        visible_reference="1",
        volume="3",
        context=context,
    )
    supplement_id = generate_doorstop_id(
        visible_reference="0",
        volume="3§1",
        context=context,
    )

    assert primary_id == "030001000000"
    assert supplement_id == "030100000000"
    assert primary_id != supplement_id


def test_reject_volume_deeper_than_reserved_namespace() -> None:
    with raises(ValueError, match="exceeds configured depth"):
        generate_doorstop_id(
            visible_reference="1",
            volume="3§1§2",
            context=DoorstopIdContext(digits=14, volume_depth=2),
        )


def test_required_width_includes_reserved_volume_hierarchy() -> None:
    from standards_atlas.adapters.doorstop.id_generator import required_doorstop_id_width

    width = required_doorstop_id_width(
        visible_reference="7.4.4.1.1",
        volume="2",
        context=DoorstopIdContext(digits=12, volume_depth=2),
    )

    assert width == 14
