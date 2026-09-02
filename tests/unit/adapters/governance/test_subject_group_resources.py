import pytest

from standards_atlas.adapters.governance import (
    ResourceGovernanceSubjectGroupProfileRepository,
)


def test_resource_repository_loads_functional_safety_profile() -> None:
    profile = ResourceGovernanceSubjectGroupProfileRepository().load(
        "functional-safety",
        "1.0.0",
    )

    assert profile.id == "functional-safety"
    assert profile.version == "1.0.0"
    assert profile.group("safety-lifecycle") is not None
    assert profile.group("safety-lifecycle").subjects == (
        "safety lifecycle",
        "software lifecycle",
    )


def test_resource_repository_rejects_unknown_profile() -> None:
    with pytest.raises(KeyError, match="subject-group profile not found"):
        ResourceGovernanceSubjectGroupProfileRepository().load("missing", "1.0.0")
