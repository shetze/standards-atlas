"""Current partial-cascade report envelope, independent of run/consensus schemas."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from standards_atlas.application.schema import require_supported_schema

PARTIAL_CASCADE_REPORT_SCHEMA_VERSION = "1.1"


def require_partial_cascade_report(payload: Mapping[str, Any]) -> None:
    """Reject obsolete or ambiguous reports before replay, inference or replacement.

    This is only the report envelope. Metrics and effective configuration must still
    agree with the independently regenerated source plan and acceptance decisions.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("partial cascade report must be an object")
    require_supported_schema("partial-cascade-report", payload.get("schema_version"))
    if payload.get("kind") != "partial-cascade-report":
        raise ValueError("not a partial cascade report")
    if type(payload.get("executed")) is not bool:
        raise ValueError("partial cascade executed flag must be explicit")
    if payload.get("run_mode") != ("executed" if payload["executed"] else "planned"):
        raise ValueError("partial cascade run mode differs from execution flag")
    if not isinstance(payload.get("effective_configuration"), dict):
        raise ValueError("partial cascade effective configuration must be explicit")
