"""Load governance subject-group profiles from packaged YAML resources."""

from __future__ import annotations

from importlib.resources import files

import yaml
from pydantic import ValidationError

from standards_atlas.domain.model import GovernanceSubjectGroupProfile


class ResourceGovernanceSubjectGroupProfileRepository:
    """Resolve immutable governance subject-group profiles shipped with Standards Atlas."""

    def load(self, profile_id: str, version: str) -> GovernanceSubjectGroupProfile:
        resource = (
            files("standards_atlas.resources")
            / "governance"
            / "subject-groups"
            / profile_id
            / version
            / "profile.yaml"
        )
        if not resource.is_file():
            raise KeyError(f"subject-group profile not found: {profile_id}@{version}")
        payload = yaml.safe_load(resource.read_text(encoding="utf-8")) or {}
        try:
            profile = GovernanceSubjectGroupProfile.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(
                f"invalid subject-group profile resource: {profile_id}@{version}: {exc}"
            ) from exc
        if profile.id != profile_id or profile.version != version:
            raise ValueError(
                "subject-group profile resource identity mismatch: "
                f"expected {profile_id}@{version}, got {profile.id}@{profile.version}"
            )
        return profile
