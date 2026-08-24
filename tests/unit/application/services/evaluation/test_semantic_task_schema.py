from __future__ import annotations

from pathlib import Path

import pytest

from standards_atlas.application.semantic_qualification.annotations import (
    StatementFunctionSelection,
)
from standards_atlas.application.semantic_qualification.proposals import SemanticTaskRepository


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
    from standards_atlas.application.semantic_qualification.annotations import (
        StatementFunctionSelection,
    )

    selection = StatementFunctionSelection.model_validate(
        {
            "statement_functions": ["description"],
            "primary_function": "description",
            "applicability_functions": ["applicability_condition"],
            "primary_applicability_function": "applicability_condition",
            "role_relation_types": [
                "excluded_from",
                "assumes_role",
            ],
            "primary_role_relation_type": "excluded_from",
            "confidence": 0.95,
            "rationale": "Applicability and responsibility are stated explicitly.",
        }
    )

    assert selection.applicability_functions[0].value == "applicability_condition"
    assert selection.role_relation_types[0].value == "excluded_from"


def test_v2_prompts_require_secondary_warning_and_condemnation_detection() -> None:
    resources = Path(
        "src/standards_atlas/resources/semantic/prompts/statement-function-classification"
    )
    prompt_paths = sorted(resources.glob("*-v2/system.txt"))

    assert prompt_paths
    for prompt_path in prompt_paths:
        prompt = prompt_path.read_text(encoding="utf-8")
        assert "do not stop after finding one dominant function" in prompt
        assert "However, be aware" in prompt
        assert "[description, warning]" in prompt
        assert "should not be regarded as complete or exhaustive" in prompt
        assert "is condemnation" in prompt
        assert "return both rather than replacing one with the other" in prompt


def test_v24_role_qualification_contract_uses_open_relation_classes() -> None:
    resources = Path("src/standards_atlas/resources/semantic")
    task, schema = SemanticTaskRepository(resources / "tasks").load(
        "semantic-profile-classification", "2.4.0"
    )

    assert "role_relation_types" not in task.ontologies
    assert "role_relation_types" not in schema["properties"]
    assert "primary_role_relation_type" not in schema["properties"]
    assert "applicability_present" in schema["required"]
    assert schema["properties"]["applicability_present"] == {"type": "boolean"}
    relation = schema["properties"]["role_relations"]["items"]
    assert relation["required"] == ["actor", "relation_class", "target"]
    properties = relation["properties"]
    assert set(properties) == {"actor", "relation_class", "target"}
    assert "relation" not in properties
    assert "enum" not in properties["relation_class"]


def test_v6_prompts_describe_open_role_relation_contract() -> None:
    resources = Path(
        "src/standards_atlas/resources/semantic/prompts/statement-function-classification"
    )
    prompt_paths = sorted(resources.glob("*-v6/system.txt"))

    assert prompt_paths
    for prompt_path in prompt_paths:
        prompt = prompt_path.read_text(encoding="utf-8")
        assert "relation_class is open" in prompt
        assert "Each role relation contains only actor, relation_class, and target" in prompt
        assert "Do not invent a missing actor" in prompt
        assert "Treat label arrays as sets" in prompt
        assert prompt.count("Applicability qualification rules:") == 1
        assert "First decide applicability_present independently from the subtype" in prompt
        assert "If applicability_present=false" in prompt
        assert "If applicability_present=true" in prompt
        assert "merely change how an activity, method, analysis, design" in prompt
        assert "rather than whether normative content is in force" in prompt
        assert "applicability of normative content itself is conditional" in prompt
        assert "Do not infer applicability merely from Scope context" in prompt
        assert '"applicability_present": false' in prompt
        assert "role_relation_types" not in prompt
        assert "primary relation type" not in prompt
