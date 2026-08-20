"""Current schema baselines before bounded compatibility is introduced."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SchemaBaseline:
    """One current schema contract and its persistence semantics."""

    family: str
    current: int | str
    compatibility_required: bool
    location: str


SCHEMA_BASELINES: dict[str, SchemaBaseline] = {
    "engineering-document": SchemaBaseline(
        "engineering-document", 3, True, ".atlas/data/documents/*.json"
    ),
    "standards-manifest": SchemaBaseline("standards-manifest", 2, True, "manifests/*.yaml"),
    "qualification-matrix-manifest": SchemaBaseline(
        "qualification-matrix-manifest", "1.5", True, "manifests/*.yaml"
    ),
    "semantic-task-resource": SchemaBaseline(
        "semantic-task-resource", 1, True, "resources/semantic/tasks/**/task.yaml"
    ),
    "semantic-taxonomy-resource": SchemaBaseline(
        "semantic-taxonomy-resource", 1, True, "resources/semantic/taxonomies/**/taxonomy.yaml"
    ),
    "structural-taxonomy-resource": SchemaBaseline(
        "structural-taxonomy-resource", 1, True, "resources/structure-taxonomies/**/taxonomy.yaml"
    ),
}


def require_current_schema(family: str, value: Any) -> None:
    """Reject anything except the clean current baseline for ``family``."""
    baseline = SCHEMA_BASELINES[family]
    if value != baseline.current:
        raise ValueError(
            f"Unsupported {family.replace('-', ' ')} schema version: {value!r}; "
            f"current baseline is {baseline.current!r}"
        )
