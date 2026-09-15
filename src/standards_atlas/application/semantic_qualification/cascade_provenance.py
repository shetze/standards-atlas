"""Current-only cascade provenance boundary; never upgrade recorded evidence."""

from __future__ import annotations

from typing import Any

from standards_atlas.application.schema import require_supported_schema

CASCADE_PROVENANCE_SCHEMA_VERSION = 1


def validate_cascade_provenance(payload: Any) -> dict[str, Any]:
    """Validate the envelope without inserting defaults or rewriting its hash input."""
    if not isinstance(payload, dict):
        raise ValueError("cascade provenance must be a JSON object")
    require_supported_schema("cascade-provenance", payload.get("schema_version"))
    return payload
