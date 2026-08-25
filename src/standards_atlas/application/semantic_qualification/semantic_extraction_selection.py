"""Shared selection helpers for semantic extraction qualification and archival."""

from __future__ import annotations

from collections.abc import Iterable

from standards_atlas.application.evaluation.models import EvaluationExample


def selected_clause_ids_by_document(
    examples: Iterable[EvaluationExample],
) -> dict[str, set[str]]:
    """Resolve document/clause coordinates from current and legacy evaluation inputs."""
    selected: dict[str, set[str]] = {}
    for example in examples:
        input_data = example.input
        context = input_data.get("context")
        coordinates = context if isinstance(context, dict) else input_data
        document_key = coordinates.get("document_key")
        clause_id = coordinates.get("clause_id")
        if isinstance(document_key, str) and isinstance(clause_id, str):
            selected.setdefault(document_key, set()).add(clause_id)
    return selected
