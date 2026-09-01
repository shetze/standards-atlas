"""Loading and serialization for governance selection profiles."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from standards_atlas.domain.model.governance_selection import GovernanceSelectionProfile


class GovernanceSelectionProfileError(ValueError):
    """Raised when a governance selection profile cannot be loaded."""


def load_governance_selection_profile(path: Path) -> GovernanceSelectionProfile:
    """Load and validate one governance selection profile from YAML."""
    if not path.is_file():
        raise GovernanceSelectionProfileError(f"Governance selection profile not found: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GovernanceSelectionProfileError(
            f"Invalid governance selection profile YAML: {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise GovernanceSelectionProfileError(
            f"Governance selection profile must contain a YAML mapping: {path}"
        )
    try:
        return GovernanceSelectionProfile.model_validate(payload)
    except ValidationError as exc:
        raise GovernanceSelectionProfileError(
            f"Invalid governance selection profile: {path}: {exc}"
        ) from exc


def render_governance_selection_profile(profile: GovernanceSelectionProfile) -> str:
    """Render canonical YAML with stable field ordering."""
    payload = profile.model_dump(mode="json", by_alias=True, exclude_none=True)
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
