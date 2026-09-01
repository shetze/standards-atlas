from pathlib import Path

import pytest

from standards_atlas.application.governance import (
    GovernanceSelectionProfileError,
    load_governance_selection_profile,
    render_governance_selection_profile,
)
from standards_atlas.domain.model import GovernanceSelectionProfile


def _payload() -> dict:
    return {
        "schema-version": 1,
        "id": "rail-onboard-sil2",
        "version": "1.0.0",
        "description": "SIL 2 onboard software development context",
        "context": {
            "domain": "railway",
            "system-types": ["onboard-software", "linux"],
            "lifecycle-phases": ["software-development", "software-validation"],
            "integrity-levels": ["SIL-2"],
            "roles": ["software-developer", "verifier"],
            "attributes": {"automation-level": "GoA4", "safety-related": True},
        },
        "standards": {
            "include": ["EN50716", "EN50126-1"],
            "exclude": ["ISO26262-11"],
        },
        "selection": {
            "process-functions": ["activity", "output"],
            "knowledge-kinds": ["process", "artifact"],
            "statement-functions": ["requirement", "conformance_statement"],
        },
        "applicability": {"require-present": True, "polarity": "included"},
    }


def test_profile_accepts_domain_neutral_engineering_context() -> None:
    profile = GovernanceSelectionProfile.model_validate(_payload())

    assert profile.id == "rail-onboard-sil2"
    assert profile.context.domain == "railway"
    assert profile.context.integrity_levels == ("SIL-2",)
    assert profile.selection.process_functions[0].value == "activity"
    assert profile.applicability.polarity == "included"


def test_profile_rejects_standard_include_exclude_overlap() -> None:
    payload = _payload()
    payload["standards"]["exclude"] = ["EN50716"]

    with pytest.raises(ValueError, match="both included and excluded"):
        GovernanceSelectionProfile.model_validate(payload)


def test_profile_rejects_unknown_fields() -> None:
    payload = _payload()
    payload["context"]["sil"] = "SIL-2"

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        GovernanceSelectionProfile.model_validate(payload)


def test_profile_rejects_polarity_without_presence_requirement() -> None:
    payload = _payload()
    payload["applicability"] = {"polarity": "included"}

    with pytest.raises(ValueError, match="requires require-present"):
        GovernanceSelectionProfile.model_validate(payload)


def test_loader_and_renderer_are_deterministic(tmp_path: Path) -> None:
    import yaml

    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(_payload(), sort_keys=False), encoding="utf-8")

    loaded = load_governance_selection_profile(path)
    rendered = render_governance_selection_profile(loaded)

    assert render_governance_selection_profile(loaded) == rendered
    assert "schema-version: 1" in rendered
    assert "system-types:" in rendered
    assert "process-functions:" in rendered


def test_loader_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text("- not\n- a\n- profile\n", encoding="utf-8")

    with pytest.raises(GovernanceSelectionProfileError, match="YAML mapping"):
        load_governance_selection_profile(path)
