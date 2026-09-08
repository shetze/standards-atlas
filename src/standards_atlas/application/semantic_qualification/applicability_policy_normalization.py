"""Normalize persisted applicability-detail contracts into policy Presence votes."""

from __future__ import annotations

from standards_atlas.application.semantic_qualification.applicability_decision_policy import (
    TriState,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailClauseResult,
    ApplicabilityDetailOutcome,
)
from standards_atlas.domain.model import ApplicabilityTarget


def normalize_detail_presence(result: ApplicabilityDetailClauseResult) -> TriState:
    """Project persisted task-v1/task-v2 detail contracts onto tri-state Presence."""

    if result.outcome is ApplicabilityDetailOutcome.FAILED:
        return None
    if result.generator is None:
        raise ValueError("generated applicability detail result is missing generator provenance")
    task_version = result.generator.task_version
    if task_version == "1.0.0":
        if result.contains_clause_or_requirement_applicability is not None:
            raise ValueError(
                "task-v1 detail result unexpectedly carries the task-v2 Presence field"
            )
        return result.applicability_target is ApplicabilityTarget.CLAUSE_OR_REQUIREMENT
    if task_version == "2.0.0":
        if result.contains_clause_or_requirement_applicability is None:
            raise ValueError(
                "v2 applicability detail result is missing clause applicability Presence"
            )
        return result.contains_clause_or_requirement_applicability
    raise ValueError(f"unsupported applicability detail task version: {task_version}")
