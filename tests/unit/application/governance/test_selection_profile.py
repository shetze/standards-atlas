from pathlib import Path

import pytest

from standards_atlas.application.governance import (
    GovernanceSelectionProfileError,
    load_governance_selection_profile,
    render_governance_selection_profile,
    resolve_governance_subject_selection,
)
from standards_atlas.domain.model import (
    GovernanceSelectionProfile,
    GovernanceSubjectGroupDefinition,
    GovernanceSubjectGroupProfile,
)


def _payload() -> dict:
    return {
        "schema-version": 2,
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
            "subject-group-profile": {"id": "functional-safety", "version": "1.0.0"},
            "primary-subjects": ["Tool Qualification"],
            "primary-subject-groups": ["safety-lifecycle"],
        },
    }


class _SubjectGroups:
    def load(self, profile_id: str, version: str) -> GovernanceSubjectGroupProfile:
        if (profile_id, version) != ("functional-safety", "1.0.0"):
            raise KeyError((profile_id, version))
        return GovernanceSubjectGroupProfile(
            id=profile_id,
            version=version,
            groups=(
                GovernanceSubjectGroupDefinition(
                    id="safety-lifecycle",
                    subjects=("Safety Lifecycle", "Software Lifecycle"),
                ),
            ),
        )


def test_profile_accepts_domain_neutral_engineering_context() -> None:
    profile = GovernanceSelectionProfile.model_validate(_payload())

    assert profile.schema_version == 2
    assert profile.id == "rail-onboard-sil2"
    assert profile.context.domain == "railway"
    assert profile.context.integrity_levels == ("SIL-2",)
    assert profile.selection.process_functions[0].value == "activity"
    assert profile.selection.primary_subjects == ("tool qualification",)
    assert profile.selection.primary_subject_groups == ("safety-lifecycle",)


def test_profile_allows_empty_statement_functions() -> None:
    payload = _payload()
    payload["selection"]["statement-functions"] = []

    profile = GovernanceSelectionProfile.model_validate(payload)

    assert profile.selection.statement_functions == ()


def test_profile_rejects_removed_applicability_contract() -> None:
    payload = _payload()
    payload["applicability"] = {"require-present": True}

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        GovernanceSelectionProfile.model_validate(payload)


def test_profile_requires_subject_group_profile_when_groups_are_used() -> None:
    payload = _payload()
    payload["selection"].pop("subject-group-profile")

    with pytest.raises(ValueError, match="requires subject-group-profile"):
        GovernanceSelectionProfile.model_validate(payload)


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


def test_subject_groups_expand_into_effective_subject_union() -> None:
    profile = GovernanceSelectionProfile.model_validate(_payload())

    resolved = resolve_governance_subject_selection(profile, _SubjectGroups())

    assert resolved.requested_groups == ("safety-lifecycle",)
    assert resolved.explicit_subjects == ("tool qualification",)
    assert resolved.effective_subjects == (
        "safety lifecycle",
        "software lifecycle",
        "tool qualification",
    )


def test_subject_group_resolution_rejects_unknown_group() -> None:
    payload = _payload()
    payload["selection"]["primary-subject-groups"] = ["unknown"]
    profile = GovernanceSelectionProfile.model_validate(payload)

    with pytest.raises(ValueError, match="unknown primary-subject-groups"):
        resolve_governance_subject_selection(profile, _SubjectGroups())


def test_loader_and_renderer_are_deterministic(tmp_path: Path) -> None:
    import yaml

    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(_payload(), sort_keys=False), encoding="utf-8")

    loaded = load_governance_selection_profile(path)
    rendered = render_governance_selection_profile(loaded)

    assert render_governance_selection_profile(loaded) == rendered
    assert "schema-version: 2" in rendered
    assert "system-types:" in rendered
    assert "primary-subjects:" in rendered
    assert "primary-subject-groups:" in rendered
    assert "applicability:" not in rendered


def test_loader_rejects_schema_version_one(tmp_path: Path) -> None:
    import yaml

    payload = _payload()
    payload["schema-version"] = 1
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(GovernanceSelectionProfileError, match="expected 2"):
        load_governance_selection_profile(path)


def test_loader_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text("- not\n- a\n- profile\n", encoding="utf-8")

    with pytest.raises(GovernanceSelectionProfileError, match="YAML mapping"):
        load_governance_selection_profile(path)
