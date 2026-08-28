"""Current bounded schema compatibility policies."""

from __future__ import annotations

from typing import Any

from .policy import SchemaPolicy

SCHEMA_POLICIES: dict[str, SchemaPolicy] = {
    "engineering-document": SchemaPolicy(
        "engineering-document", 7, (7,), ".atlas/data/documents/*.json"
    ),
    "standards-manifest": SchemaPolicy("standards-manifest", 2, (2,), "manifests/*.yaml"),
    "qualification-matrix-manifest": SchemaPolicy(
        "qualification-matrix-manifest", "1.5", ("1.5",), "manifests/*.yaml"
    ),
    "semantic-task-resource": SchemaPolicy(
        "semantic-task-resource", 1, (1,), "resources/semantic/tasks/**/task.yaml"
    ),
    "semantic-profile-resource": SchemaPolicy(
        "semantic-profile-resource", 1, (1,), "resources/semantic/profiles/**/profile.yaml"
    ),
    "ontology-resource": SchemaPolicy(
        "ontology-resource", 1, (1,), "resources/ontologies/**/ontology.yaml"
    ),
    "formal-ontology-resource": SchemaPolicy(
        "formal-ontology-resource", 1, (1,), "resources/formal_ontologies/**/ontology.yaml"
    ),
    "formal-semantic-projection": SchemaPolicy(
        "formal-semantic-projection", 1, (1,), ".atlas/data/formal-semantic-projections/*.json"
    ),
    "semantic-extraction": SchemaPolicy(
        "semantic-extraction", 1, (1,), ".atlas/data/semantic-extractions/*.json"
    ),
    "structural-taxonomy-resource": SchemaPolicy(
        "structural-taxonomy-resource",
        1,
        (1,),
        "resources/structure-taxonomies/**/taxonomy.yaml",
    ),
}

# Compatibility alias for code/docs created by the baseline slice.
SCHEMA_BASELINES = SCHEMA_POLICIES
SchemaBaseline = SchemaPolicy


def require_supported_schema(family: str, value: Any) -> None:
    """Validate that ``value`` is inside the bounded reader support window."""
    SCHEMA_POLICIES[family].require_readable(value)


def require_current_schema(family: str, value: Any) -> None:
    """Validate writer-side current schema output."""
    SCHEMA_POLICIES[family].require_current_for_write(value)
