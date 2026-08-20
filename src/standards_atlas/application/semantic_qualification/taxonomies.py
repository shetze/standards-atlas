"""Versioned semantic taxonomy contracts independent from evaluation tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.schema import require_supported_schema


class SemanticTaxonomyDefinition(BaseModel):
    """One independently versioned semantic label space."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    description: str = ""
    values: tuple[str, ...] = Field(min_length=1)
    semantics: dict[str, Any] = Field(default_factory=dict)
    codes: dict[str, str] = Field(default_factory=dict)


class SemanticTaxonomyReference(BaseModel):
    """Reference from a semantic task to an independently versioned taxonomy."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class SemanticTaxonomyRepository:
    """Load semantic taxonomies without coupling their lifecycle to a task version."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def load(self, taxonomy_id: str, version: str) -> SemanticTaxonomyDefinition:
        path = self._root / taxonomy_id / version / "taxonomy.yaml"
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        require_supported_schema("semantic-taxonomy-resource", payload.get("schema_version"))
        definition = SemanticTaxonomyDefinition.model_validate(payload)
        if definition.id != taxonomy_id or definition.version != version:
            raise ValueError(
                "semantic taxonomy identity does not match resource path: "
                f"expected {taxonomy_id}:{version}, got {definition.id}:{definition.version}"
            )
        return definition
