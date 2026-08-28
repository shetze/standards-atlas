"""Packaged-resource adapter for ontology definitions."""

from __future__ import annotations

from pathlib import Path

import yaml

from standards_atlas.application.schema import require_supported_schema

from .definition import OntologyDefinition


class ResourceOntologyDefinitionRepository:
    """Load ontology definitions from versioned packaged YAML resources."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(__file__).parents[2] / "resources" / "ontologies"

    def load(self, ontology_id: str, version: str) -> OntologyDefinition:
        path = self._root / ontology_id / version / "ontology.yaml"
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        require_supported_schema("ontology-resource", payload.get("schema_version"))
        definition = OntologyDefinition.model_validate(payload)
        if definition.id != ontology_id or definition.version != version:
            raise ValueError(
                "ontology identity does not match resource path: "
                f"expected {ontology_id}:{version}, got {definition.id}:{definition.version}"
            )
        return definition
