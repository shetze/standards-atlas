from __future__ import annotations

from pathlib import Path

import pytest

from standards_atlas.application.services.evaluation.annotations import SemanticRoleSelection
from standards_atlas.application.services.evaluation.proposals import SemanticTaskRepository


def test_semantic_role_schema_uses_codex_supported_array_constraints() -> None:
    resources = Path("src/standards_atlas/resources/semantic/tasks")
    _, schema = SemanticTaskRepository(resources).load("semantic-role-classification", "1.0.0")

    semantic_roles = schema["properties"]["semantic_roles"]

    assert "uniqueItems" not in semantic_roles


def test_duplicate_semantic_roles_are_rejected_after_provider_response() -> None:
    with pytest.raises(ValueError, match="must not contain duplicates"):
        SemanticRoleSelection.model_validate(
            {
                "semantic_roles": ["requirements", "requirements"],
                "primary_role": "requirements",
                "confidence": 0.8,
                "rationale": "Normative requirement.",
            }
        )
