"""Draft 2020-12 JSON-schema validation for generated semantic artefacts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError


def validate_schema(value: Mapping[str, Any], schema: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Validate one value and retain the legacy single-error result contract."""
    errors = validate_schema_errors(value, schema)
    return (not errors, errors[0] if errors else None)


def validate_schema_errors(value: Mapping[str, Any], schema: Mapping[str, Any]) -> tuple[str, ...]:
    """Return every deterministic Draft 2020-12 validation error."""
    validate_schema_definition(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=_validation_error_key)
    return tuple(_format_validation_error(error) for error in errors)


def validate_schema_definition(schema: Mapping[str, Any]) -> None:
    """Reject malformed output schemas before an LLM request is attempted."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        path = _json_path(error.absolute_schema_path)
        raise ValueError(
            f"invalid Draft 2020-12 output schema at {path}: {error.message}"
        ) from error


def _validation_error_key(error: ValidationError) -> tuple[tuple[str, ...], str]:
    return tuple(str(item) for item in error.absolute_path), error.message


def _format_validation_error(error: ValidationError) -> str:
    return f"{_json_path(error.absolute_path)}: {error.message}"


def _json_path(parts: Iterable[str | int]) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path
