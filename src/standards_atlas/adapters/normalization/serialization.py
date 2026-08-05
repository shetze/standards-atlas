"""Canonical serialization helpers for normalized document artifacts."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from standards_atlas.shared.hashing import sha256_text


def canonical_json(value: BaseModel | dict[str, Any]) -> str:
    """Return a stable UTF-8 JSON representation with a final newline."""
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        )
        + "\n"
    )


def canonical_sha256(value: BaseModel | dict[str, Any]) -> str:
    """Hash the canonical JSON representation of an artifact payload."""
    return sha256_text(canonical_json(value))
