from __future__ import annotations

from pathlib import Path

import pytest

from standards_atlas.application.services.evaluation.annotations import StatementFunctionSelection
from standards_atlas.application.services.evaluation.proposals import SemanticTaskRepository


def test_semantic_role_schema_uses_codex_supported_array_constraints() -> None:
    resources = Path("src/standards_atlas/resources/semantic/tasks")
    _, schema = SemanticTaskRepository(resources).load("statement-function-classification", "1.0.0")

    statement_functions = schema["properties"]["statement_functions"]

    assert "uniqueItems" not in statement_functions


def test_duplicate_statement_functions_are_rejected_after_provider_response() -> None:
    with pytest.raises(ValueError, match="must not contain duplicates"):
        StatementFunctionSelection.model_validate(
            {
                "statement_functions": ["requirement", "requirement"],
                "primary_function": "requirement",
                "confidence": 0.8,
                "rationale": "Normative requirement.",
            }
        )


def test_statement_function_primary_function_uses_codex_compatible_nullable_enum() -> None:
    resources = Path("src/standards_atlas/resources/semantic")
    schema_paths = sorted(resources.rglob("statement-function-classification/**/schema.json"))

    assert schema_paths
    for schema_path in schema_paths:
        import json

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        primary_function = schema["properties"]["primary_function"]

        assert "anyOf" not in primary_function
        assert primary_function["type"] == ["string", "null"]
        assert primary_function["enum"][-1] is None


def test_multidimensional_selection_accepts_applicability_and_responsibility() -> None:
    from standards_atlas.application.services.evaluation.annotations import (
        StatementFunctionSelection,
    )

    selection = StatementFunctionSelection.model_validate(
        {
            "statement_functions": ["description"],
            "primary_function": "description",
            "applicability_functions": ["applicability_condition"],
            "primary_applicability_function": "applicability_condition",
            "responsibility_functions": [
                "responsibility_exclusion",
                "role_condition",
            ],
            "primary_responsibility_function": "responsibility_exclusion",
            "confidence": 0.95,
            "rationale": "Applicability and responsibility are stated explicitly.",
        }
    )

    assert selection.applicability_functions[0].value == "applicability_condition"
    assert selection.responsibility_functions[0].value == "responsibility_exclusion"
