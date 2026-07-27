"""Minimal JSON-schema validation for generated semantic artefacts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def validate_schema(value: Mapping[str, Any], schema: Mapping[str, Any]) -> tuple[bool, str | None]:
    required = schema.get("required", ())
    for key in required:
        if key not in value:
            return False, f"missing required property: {key}"
    properties = schema.get("properties", {})
    for key, item in value.items():
        definition = properties.get(key)
        if definition is not None and not _matches_type(item, definition.get("type")):
            return False, f"property {key} has invalid type"
    if schema.get("additionalProperties") is False:
        unexpected = set(value) - set(properties)
        if unexpected:
            return False, f"unexpected properties: {', '.join(sorted(unexpected))}"
    return True, None


def _matches_type(value: Any, expected: str | None) -> bool:
    if expected is None:
        return True
    return {
        "string": lambda: isinstance(value, str),
        "number": lambda: isinstance(value, int | float) and not isinstance(value, bool),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "boolean": lambda: isinstance(value, bool),
        "object": lambda: isinstance(value, Mapping),
        "array": lambda: isinstance(value, list),
        "null": lambda: value is None,
    }.get(expected, lambda: True)()
