from __future__ import annotations

from itertools import product

from standards_atlas.application.semantic_qualification.applicability_decision_policy import (
    decide_detail_presence,
    decide_final_presence,
    tri_and,
    tri_or,
)

TRI = (False, True, None)


def _expected_and(left: bool | None, right: bool | None) -> bool | None:
    if False in (left, right):
        return False
    if left is True and right is True:
        return True
    return None


def _expected_or(left: bool | None, right: bool | None) -> bool | None:
    if True in (left, right):
        return True
    if left is False and right is False:
        return False
    return None


def test_three_valued_operators_cover_all_pairs() -> None:
    for left, right in product(TRI, repeat=2):
        assert tri_and(left, right) is _expected_and(left, right)
        assert tri_or(left, right) is _expected_or(left, right)


def test_policy_covers_all_27_three_valued_combinations() -> None:
    for primary, rescue, confirmation in product(TRI, repeat=3):
        expected = _expected_or(primary, _expected_and(rescue, confirmation))
        assert (
            decide_detail_presence(
                primary=primary,
                rescue=rescue,
                confirmation=confirmation,
            )
            is expected
        )


def test_negative_presence_gate_is_decisive() -> None:
    for detail_present in TRI:
        assert decide_final_presence(gate_present=False, detail_present=detail_present) is False


def test_positive_presence_gate_preserves_detail_unknown() -> None:
    assert decide_final_presence(gate_present=True, detail_present=None) is None
