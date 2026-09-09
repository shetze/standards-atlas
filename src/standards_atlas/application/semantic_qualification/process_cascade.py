"""Opt-in process escalation and independent, monotonic primary/set snapshots."""

from __future__ import annotations

from typing import Any

from .process_functions import PROCESS_PRIMARY_FIELDS, PROCESS_SET_FIELDS

PROCESS_PRIMARY_REASONS = frozenset(
    (
        "insufficient_process_function_models",
        "process_function_unavailable",
        "process_function_disagreement",
        "process_function_confidence",
        "process_function_resolver_confidence",
    )
)
PROCESS_SET_REASONS = frozenset(
    (
        "insufficient_process_set_models",
        "process_set_unavailable",
        "process_set_disagreement",
        "process_set_confidence",
    )
)


def process_escalation_reasons(
    clause: Any, resolution: Any, *, resolver: bool = False
) -> tuple[str, ...]:
    """Never turn missing observations into unanimous negatives.

    Escalation is opt-in so upgrading a manifest does not silently expand model
    workload. Without opt-in the dimension is still measured and persisted.
    """
    reasons = []
    for dimension, prefix, enabled, threshold, count in (
        (
            "function", "process_primary", resolution.escalate_on_process_function_disagreement,
            resolution.minimum_process_function_confidence,
            getattr(clause, "process_primary_participating_models", 0),
        ),
        (
            "set", "process_set", resolution.escalate_on_process_set_disagreement,
            resolution.minimum_process_set_confidence,
            getattr(clause, "process_participating_models", 0),
        ),
    ):
        if not enabled and threshold is None:
            continue
        required = resolution.minimum_successful_models
        if resolver and dimension == "function":
            required = 1
            threshold = resolution.process_function_resolver_min_confidence
        if count < required:
            reasons.append(f"insufficient_process_{dimension}_models")
        if not getattr(clause, f"{prefix}_evaluated", False):
            reasons.append(f"process_{dimension}_unavailable")
            continue
        if not getattr(clause, f"{prefix}_decided", False):
            reasons.append(f"process_{dimension}_disagreement")
        elif threshold is not None:
            if getattr(clause, f"{prefix}_confidence", 0.0) < threshold:
                suffix = (
                    "resolver_confidence" if resolver and dimension == "function" else "confidence"
                )
                reasons.append(f"process_{dimension}_{suffix}")
        elif not getattr(clause, f"{prefix}_unanimous", False):
            reasons.append(f"process_{dimension}_disagreement")
    return tuple(reasons)


def process_stage_reasons(
    cumulative_clause: Any, stage_clause: Any, previous_reasons: tuple[str, ...], resolution: Any
) -> tuple[str, ...]:
    previous = set(previous_reasons)
    cumulative = process_escalation_reasons(cumulative_clause, resolution)
    primary = cumulative
    if resolution.process_function_resolution_mode == "stage_resolver":
        primary = process_escalation_reasons(stage_clause, resolution, resolver=True)
    return tuple(
        reason for reason in primary
        if previous & PROCESS_PRIMARY_REASONS and reason in PROCESS_PRIMARY_REASONS
    ) + tuple(
        reason for reason in cumulative
        if previous & PROCESS_SET_REASONS and reason in PROCESS_SET_REASONS
    )


def capture_process_dimensions(
    *, cumulative_clause: Any, stage_clause: Any, previous_reasons: tuple[str, ...],
    remaining_reasons: tuple[str, ...], source: str, initial_stage: bool, resolution: Any,
) -> dict[str, dict[str, Any]]:
    captured = {}
    previous, remaining = set(previous_reasons), set(remaining_reasons)
    resolver = not initial_stage and resolution.process_function_resolution_mode == "stage_resolver"
    for dimension, fields, prefix, reason_set, clause in (
        (
            "process_function", PROCESS_PRIMARY_FIELDS, "process_primary", PROCESS_PRIMARY_REASONS,
            stage_clause if resolver else cumulative_clause,
        ),
        ("process_set", PROCESS_SET_FIELDS, "process_set", PROCESS_SET_REASONS, cumulative_clause),
    ):
        just_resolved = (
            not remaining & reason_set if initial_stage
            else bool(previous & reason_set) and not remaining & reason_set
        )
        category = getattr(clause, f"{prefix}_category", None)
        if (
            not just_resolved
            or not getattr(clause, f"{prefix}_decided", False)
            or category is None
            or category.value not in resolution.accepted_categories
        ):
            continue
        captured[dimension] = {field: getattr(clause, field) for field in fields}
        captured[dimension]["source"] = (
            f"{source}/stage-resolver" if resolver and dimension == "process_function" else source
        )
    return captured
