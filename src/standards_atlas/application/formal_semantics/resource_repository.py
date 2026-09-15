"""Packaged repository for formal OWL ontology resources."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from standards_atlas.application.schema import require_supported_schema

from .ontology_definition import FormalOntologyDefinition

_TERM = re.compile(r"^stat:([A-Za-z][A-Za-z0-9_-]*)\s+a\s+([^.;]+)", re.MULTILINE)


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
        resource = base / definition.resource
        if not resource.is_file():
            raise ValueError(f"formal ontology resource does not exist: {definition.resource}")
        self._validate_extraction_vocabulary(definition, resource.read_text(encoding="utf-8"))
        return definition

    def read_text(self, ontology_id: str, version: str) -> str:
        definition = self.load(ontology_id, version)
        return (self._root / ontology_id / version / definition.resource).read_text(
            encoding="utf-8"
        )

    @staticmethod
    def _validate_extraction_vocabulary(
        definition: FormalOntologyDefinition,
        text: str,
    ) -> None:
        classes: set[str] = set()
        properties: set[str] = set()
        for local_name, rdf_types in _TERM.findall(text):
            if "owl:Class" in rdf_types:
                classes.add(local_name)
            if any(
                token in rdf_types
                for token in ("owl:ObjectProperty", "owl:DatatypeProperty", "rdf:Property")
            ):
                properties.add(local_name)
        missing_classes = set(definition.extraction_vocabulary.classes) - classes
        missing_properties = set(definition.extraction_vocabulary.properties) - properties
        if missing_classes or missing_properties:
            details = []
            if missing_classes:
                details.append(f"classes={sorted(missing_classes)!r}")
            if missing_properties:
                details.append(f"properties={sorted(missing_properties)!r}")
            raise ValueError(
                "formal ontology extraction vocabulary contains undeclared terms: "
                + ", ".join(details)
            )
