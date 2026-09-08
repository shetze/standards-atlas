"""Deterministic applicability decision policy over normalized detail Presence votes."""

from __future__ import annotations

type TriState = bool | None

POLICY_ID = "mistral-v4-or-v3-and-v1"
POLICY_VERSION = "1.0.0"


def tri_and(left: TriState, right: TriState) -> TriState:
    """Kleene-style AND with decisive false values."""

    if left is False or right is False:
        return False
    if left is True and right is True:
        return True
    return None


def tri_or(left: TriState, right: TriState) -> TriState:
    """Kleene-style OR with decisive true values."""

    if left is True or right is True:
        return True
    if left is False and right is False:
        return False
    return None


def decide_detail_presence(
    *, primary: TriState, rescue: TriState, confirmation: TriState
) -> TriState:
    """Apply D4 OR (D3 AND D1) to normalized detail Presence decisions."""

    return tri_or(primary, tri_and(rescue, confirmation))


def decide_final_presence(*, gate_present: bool, detail_present: TriState) -> TriState:
    """Apply the fixed Presence gate used by Slice 9."""

    if not gate_present:
        return False
    return detail_present
