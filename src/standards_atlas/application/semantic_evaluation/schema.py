"""Small deterministic JSON Schema validator for structured evaluation outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class SchemaValidationError(ValueError):
    """Raised when a generated JSON value violates its declared schema."""


def validate_json_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, Mapping):
            raise SchemaValidationError(f"{path} must be an object")
        required = schema.get("required", ())
        for key in required:
            if key not in value:
                raise SchemaValidationError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                validate_json_schema(item, properties[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise SchemaValidationError(f"{path}.{key} is not allowed")
    elif expected_type == "array":
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise SchemaValidationError(f"{path} must be an array")
        item_schema = schema.get("items", {})
        for index, item in enumerate(value):
            validate_json_schema(item, item_schema, f"{path}[{index}]")
    elif expected_type == "string" and not isinstance(value, str):
        raise SchemaValidationError(f"{path} must be a string")
    elif expected_type == "number" and (
        not isinstance(value, (int, float)) or isinstance(value, bool)
    ):
        raise SchemaValidationError(f"{path} must be a number")
    elif expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise SchemaValidationError(f"{path} must be an integer")
    elif expected_type == "boolean" and not isinstance(value, bool):
        raise SchemaValidationError(f"{path} must be a boolean")
    elif expected_type == "null" and value is not None:
        raise SchemaValidationError(f"{path} must be null")

    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path} must be one of {schema['enum']}")
