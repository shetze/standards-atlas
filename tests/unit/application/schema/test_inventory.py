from __future__ import annotations

from standards_atlas.application.schema import (
    SCHEMA_POLICIES,
    VERSIONED_INTERFACES,
    LifecycleBoundary,
    VersionAxis,
    schema_managed_interfaces,
)


def test_every_schema_managed_interface_has_a_central_policy() -> None:
    families = {item.schema_family for item in schema_managed_interfaces()}
    assert families == set(SCHEMA_POLICIES)


def test_schema_and_resource_versions_are_independent_for_semantic_resources() -> None:
    by_id = {item.id: item for item in VERSIONED_INTERFACES}
    for interface_id in (
        "semantic-task",
        "semantic-profile",
        "semantic-ontology",
        "structural-taxonomy",
        "formal-ontology",
    ):
        assert by_id[interface_id].axes == (VersionAxis.SCHEMA, VersionAxis.RESOURCE)


def test_prompt_version_is_a_resource_axis_not_a_serialisation_schema() -> None:
    prompt = next(item for item in VERSIONED_INTERFACES if item.id == "semantic-prompt")
    assert prompt.axes == (VersionAxis.RESOURCE,)
    assert prompt.schema_family is None
    assert prompt.boundary is LifecycleBoundary.PACKAGED_RESOURCE


def test_runtime_publication_view_is_not_a_versioned_interface() -> None:
    assert "publication-document" not in {item.id for item in VERSIONED_INTERFACES}
