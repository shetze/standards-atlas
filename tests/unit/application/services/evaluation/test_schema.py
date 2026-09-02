from __future__ import annotations

import pytest

from standards_atlas.application.evaluation.schema import (
    validate_schema,
    validate_schema_definition,
    validate_schema_errors,
)

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "confidence"],
                "properties": {
                    "kind": {"type": "string", "enum": ["requirement", "note"]},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
            },
        }
    },
}


def test_validates_nested_draft_2020_12_constraints() -> None:
    errors = validate_schema_errors(
        {
            "items": [
                {"kind": "unknown", "confidence": 1.5, "extra": True},
            ]
        },
        SCHEMA,
    )

    assert any("$.items[0].kind" in error and "not one of" in error for error in errors)
    assert any("$.items[0].confidence" in error and "greater than" in error for error in errors)
    assert any("$.items[0]" in error and "Additional properties" in error for error in errors)
    assert validate_schema({"items": []}, SCHEMA)[0] is False


def test_rejects_invalid_schema_definition_before_validation() -> None:
    with pytest.raises(ValueError, match="invalid Draft 2020-12 output schema"):
        validate_schema_definition({"type": "not-a-json-schema-type"})
