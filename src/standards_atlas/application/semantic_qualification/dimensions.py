"""Task-to-dimension contracts for split semantic qualification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from standards_atlas.application.semantic_qualification.annotations import (
    StatementFunctionSelection,
)


@dataclass(frozen=True)
class QualificationDimension:
    """Selection fields scored for one semantic task."""

    name: str
    values_field: str
    primary_field: str | None

    def values(self, selection: StatementFunctionSelection) -> tuple[Enum, ...]:
        return tuple(getattr(selection, self.values_field))

    def primary(self, selection: StatementFunctionSelection) -> Enum | None:
        if self.primary_field is None:
            return None
        return getattr(selection, self.primary_field)


_TASK_DIMENSIONS: dict[str, QualificationDimension] = {
    "statement-function-classification": QualificationDimension(
        "statement_functions", "statement_functions", "primary_function"
    ),
    "semantic-profile-classification": QualificationDimension(
        "statement_functions", "statement_functions", "primary_function"
    ),
    "knowledge-kind-classification": QualificationDimension(
        "knowledge_kinds", "knowledge_kinds", "primary_knowledge_kind"
    ),
    "process-function-classification": QualificationDimension(
        "process_functions", "process_functions", "primary_process_function"
    ),
    "applicability-extraction": QualificationDimension(
        "applicability_functions", "applicability_functions", "primary_applicability_function"
    ),
    "role-relation-extraction": QualificationDimension(
        "role_relation_types", "role_relation_types", "primary_role_relation_type"
    ),
}


def qualification_dimension(task: str) -> QualificationDimension:
    """Return the scoring projection for a semantic task."""

    try:
        return _TASK_DIMENSIONS[task]
    except KeyError as exc:
        raise ValueError(f"unsupported semantic qualification task: {task!r}") from exc
