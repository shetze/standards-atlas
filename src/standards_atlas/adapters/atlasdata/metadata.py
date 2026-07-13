"""Parse metadata headers from Atlas data files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AtlasMetadata:
    """Metadata describing one Atlas standard data file."""

    name: str
    digits: int
    parent: str | None = None
    part_shift: int = 0
    part_digits: int = 0
    official_year: int | None = None
    extra_fields: dict[str, str] = field(default_factory=dict)


_REQUIRED_FIELDS = {"name", "digits"}

_FIELD_ALIASES = {
    "partShift": "part_shift",
    "partDigits": "part_digits",
    "oyr": "official_year",
}


_INT_FIELDS = {
    "digits",
    "part_shift",
    "part_digits",
    "official_year",
}


def parse_metadata(text: str) -> AtlasMetadata:
    """Parse the metadata header of an Atlas data file.

    Parsing stops before the structure block. The function treats the file as
    declarative data and does not execute shell code.
    """
    raw_fields: dict[str, str] = {}

    for line in text.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("structure="):
            break

        if "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = _normalize_value(value.strip())

        normalized_key = _FIELD_ALIASES.get(key, key)
        raw_fields[normalized_key] = value

    missing = _REQUIRED_FIELDS - raw_fields.keys()
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Missing required metadata field(s): {missing_list}")

    known_values: dict[str, Any] = {}
    extra_fields: dict[str, str] = {}

    for key, value in raw_fields.items():
        if key in AtlasMetadata.__dataclass_fields__ and key != "extra_fields":
            known_values[key] = _convert_value(key, value)
        else:
            extra_fields[key] = value

    return AtlasMetadata(
        name=known_values["name"],
        digits=known_values["digits"],
        parent=known_values.get("parent"),
        part_shift=known_values.get("part_shift", 0),
        part_digits=known_values.get("part_digits", 0),
        official_year=known_values.get("official_year"),
        extra_fields=extra_fields,
    )


def _normalize_value(value: str) -> str:
    """Normalize a shell-like metadata value."""
    if _is_quoted(value):
        return value[1:-1]

    return value


def _is_quoted(value: str) -> bool:
    return len(value) >= 2 and (
        value.startswith('"')
        and value.endswith('"')
        or value.startswith("'")
        and value.endswith("'")
    )


def _convert_value(key: str, value: str) -> int | str:
    if key in _INT_FIELDS:
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"Metadata field {key!r} must be an integer, got {value!r}.") from exc

    return value
