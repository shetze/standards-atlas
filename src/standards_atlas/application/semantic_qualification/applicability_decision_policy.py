"""Deterministic applicability decision policy over normalized detail Presence votes."""

from __future__ import annotations

type TriState = bool | None

POLICY_ID = "mistral-v4-or-v3-and-v1"
POLICY_VERSION = "1.0.0"
POLICY_EXPRESSION = "D4 OR (D3 AND D1)"
POLICY_MODEL_ID = "mistral-small-3.2-24b-instruct-q4-k-m"


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
    """Apply the fixed Presence-positive detail gate."""

    if not gate_present:
        return False
    return detail_present


def rescue_is_required(primary: TriState) -> bool:
    """Return whether D3 can still affect the policy result after D4."""

    return primary is not True


def confirmation_is_required(*, primary: TriState, rescue: TriState) -> bool:
    """Return whether observing D1 can still change the policy result.

    This deliberately reasons over all possible D1 values.  It therefore keeps the
    failed-D3/negative-D4 case routable to D1 while avoiding a pointless D1 request
    when D4 and D3 are both unknown (the final result remains unknown either way).
    """

    outcomes = {
        decide_detail_presence(primary=primary, rescue=rescue, confirmation=value)
        for value in (False, True, None)
    }
    return len(outcomes) > 1
