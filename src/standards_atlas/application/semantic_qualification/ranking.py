"""Ranking and Pareto analysis for qualification candidates."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CandidateQualification,
        RegressionThresholds,
    )


def candidate_key(candidate: CandidateQualification) -> str:
    """Return the stable human-readable key of a candidate."""
    return f"{candidate.prompt_id} / {candidate.model_id} / {candidate.reasoning_mode_id}"


def apply_baseline(
    candidates: list[CandidateQualification],
    thresholds: RegressionThresholds,
) -> tuple[CandidateQualification, ...]:
    """Apply the configured baseline threshold to all candidates."""
    baseline = find_baseline(candidates, thresholds)
    return tuple(apply_baseline_threshold(item, baseline, thresholds) for item in candidates)


def find_baseline(
    candidates: list[CandidateQualification],
    thresholds: RegressionThresholds,
) -> CandidateQualification | None:
    """Find the configured baseline candidate, when present."""
    if thresholds.baseline_prompt_id is None or thresholds.baseline_model_id is None:
        return None
    return next(
        (
            item
            for item in candidates
            if item.prompt_id == thresholds.baseline_prompt_id
            and item.model_id == thresholds.baseline_model_id
            and item.reasoning_mode_id == thresholds.baseline_reasoning_mode_id
        ),
        None,
    )


def apply_baseline_threshold(
    candidate: CandidateQualification,
    baseline: CandidateQualification | None,
    thresholds: RegressionThresholds,
) -> CandidateQualification:
    """Apply the allowed Gold-F1 drop relative to the baseline."""
    if baseline is None:
        return candidate
    if baseline.mean_gold_f1 is None or candidate.mean_gold_f1 is None:
        return candidate
    minimum = baseline.mean_gold_f1 - thresholds.max_gold_f1_drop
    if candidate.mean_gold_f1 >= minimum:
        return candidate
    regressions = candidate.regressions + (
        f"mean Gold F1 {candidate.mean_gold_f1:.4f} < baseline allowance {minimum:.4f}",
    )
    return candidate.model_copy(update={"passed": False, "regressions": regressions})


def pareto_front(candidates: tuple[CandidateQualification, ...]) -> set[str]:
    """Return candidate keys on the Pareto front."""
    complete = [item for item in candidates if item.qualification_eligible]
    front: set[str] = set()
    for candidate in complete:
        dominated = any(
            other is not candidate and dominates(other, candidate) for other in complete
        )
        if not dominated:
            front.add(candidate_key(candidate))
    return front


def dominates(left: CandidateQualification, right: CandidateQualification) -> bool:
    """Return whether left is no worse and strictly better in one dimension."""
    left_duration = (
        left.mean_duration_seconds if left.mean_duration_seconds is not None else math.inf
    )
    right_duration = (
        right.mean_duration_seconds if right.mean_duration_seconds is not None else math.inf
    )
    left_memory = left.peak_memory_gb if left.peak_memory_gb is not None else math.inf
    right_memory = right.peak_memory_gb if right.peak_memory_gb is not None else math.inf
    left_f1 = left.mean_gold_f1 if left.mean_gold_f1 is not None else -1.0
    right_f1 = right.mean_gold_f1 if right.mean_gold_f1 is not None else -1.0
    left_stddev = left.gold_f1_stddev if left.gold_f1_stddev is not None else math.inf
    right_stddev = right.gold_f1_stddev if right.gold_f1_stddev is not None else math.inf
    no_worse = (
        left_f1 >= right_f1
        and left_stddev <= right_stddev
        and left_duration <= right_duration
        and left_memory <= right_memory
    )
    strictly_better = (
        left_f1 > right_f1
        or left_stddev < right_stddev
        or left_duration < right_duration
        or left_memory < right_memory
    )
    return no_worse and strictly_better


def rank_candidates(candidates: tuple[CandidateQualification, ...]) -> tuple[str, ...]:
    """Rank qualification-eligible candidates using the existing sort policy."""
    rankable = [item for item in candidates if item.qualification_eligible]
    return tuple(
        candidate_key(item)
        for item in sorted(
            rankable,
            key=lambda item: (
                item.passed,
                item.mean_gold_f1 if item.mean_gold_f1 is not None else -1.0,
                -(item.gold_f1_stddev or 0.0),
                item.mean_gold_coverage if item.mean_gold_coverage is not None else -1.0,
                -(item.mean_duration_seconds or math.inf),
            ),
            reverse=True,
        )
    )
