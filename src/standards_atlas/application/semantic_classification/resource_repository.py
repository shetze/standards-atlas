"""Packaged-resource adapter for versioned semantic profiles."""

from __future__ import annotations

from pathlib import Path

import yaml

from standards_atlas.application.schema import require_supported_schema

from .profile import SemanticProfile


class ResourceSemanticProfileRepository:
    """Load semantic profiles from versioned packaged YAML resources."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(__file__).parents[2] / "resources" / "semantic" / "profiles"

    def load(self, profile_id: str, version: str) -> SemanticProfile:
        path = self._root / profile_id / version / "profile.yaml"
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        require_supported_schema("semantic-profile-resource", payload.get("schema_version"))
        profile = SemanticProfile.model_validate(payload)
        if profile.id != profile_id or profile.version != version:
            raise ValueError(
                "semantic profile identity does not match resource path: "
                f"expected {profile_id}:{version}, got {profile.id}:{profile.version}"
            )
        return profile
