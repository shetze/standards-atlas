"""Packaged repository for formal OWL ontology resources."""

from __future__ import annotations

from pathlib import Path

import yaml

from standards_atlas.application.schema import require_supported_schema

from .ontology_definition import FormalOntologyDefinition


class ResourceFormalOntologyRepository:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(__file__).parents[2] / "resources" / "formal_ontologies"

    def load(self, ontology_id: str, version: str) -> FormalOntologyDefinition:
        base = self._root / ontology_id / version
        payload = yaml.safe_load((base / "ontology.yaml").read_text(encoding="utf-8")) or {}
        require_supported_schema("formal-ontology-resource", payload.get("schema_version"))
        definition = FormalOntologyDefinition.model_validate(payload)
        if definition.id != ontology_id or definition.version != version:
            raise ValueError("formal ontology identity does not match resource path")
        if not (base / definition.resource).is_file():
            raise ValueError(f"formal ontology resource does not exist: {definition.resource}")
        return definition

    def read_text(self, ontology_id: str, version: str) -> str:
        definition = self.load(ontology_id, version)
        return (self._root / ontology_id / version / definition.resource).read_text(
            encoding="utf-8"
        )
