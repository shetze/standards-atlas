"""Shared clause and dimension accounting for execution and offline replay."""

from __future__ import annotations

from collections import Counter

DIMENSIONS = (
    "statement_function",
    "knowledge_kind",
    "process_function",
    "process_set",
    "applicability",
    "role_relation",
)


def resolution_counts(resolutions: dict) -> dict[str, int]:
    return {
        dimension: sum(dimension in clause for clause in resolutions.values())
        for dimension in DIMENSIONS
    }


def reason_counts(reasons: dict[str, tuple[str, ...]]) -> dict[str, int]:
    return dict(sorted(Counter(reason for values in reasons.values() for reason in values).items()))


def stage_accounting(
    *,
    clause_ids: tuple[str, ...],
    reasons: dict[str, tuple[str, ...]],
    selected_count: int,
) -> dict[str, object]:
    if set(clause_ids) != set(reasons):
        raise ValueError("every entered clause must have an explicit cascade outcome")
    completed = [clause_id for clause_id in clause_ids if not reasons[clause_id]]
    missing = [
        clause_id
        for clause_id in clause_ids
        if any(reason.endswith("consensus_result") for reason in reasons[clause_id])
    ]
    return {
        "selected_clause_count": selected_count,
        "accounted_clause_count": len(clause_ids),
        "completed_clause_count": len(completed),
        "completed_clause_ids": completed,
        "completed_fraction_of_selection": (
            len(completed) / selected_count if selected_count else 0.0
        ),
        "missing_consensus_clause_count": len(missing),
        "missing_consensus_clause_ids": missing,
    }
