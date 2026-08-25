"""Small provider-neutral vocabulary index over packaged Turtle ontologies."""

from __future__ import annotations

import re
from dataclasses import dataclass

from standards_atlas.application.formal_semantics import ResourceFormalOntologyRepository
from standards_atlas.domain.model import FORMAL_SEMANTIC_NAMESPACE

_TERM = re.compile(r"^stat:([A-Za-z][A-Za-z0-9_-]*)\s+a\s+([^.;]+)", re.MULTILINE)


@dataclass(frozen=True)
class FormalOntologyVocabulary:
    classes: frozenset[str]
    properties: frozenset[str]

    @classmethod
    def load(
        cls,
        ontology_versions: tuple[str, ...],
        *,
        repository: ResourceFormalOntologyRepository | None = None,
    ) -> FormalOntologyVocabulary:
        repo = repository or ResourceFormalOntologyRepository()
        classes: set[str] = set()
        properties: set[str] = set()
        for item in ontology_versions:
            ontology_id, version = item.split("@", 1)
            text = repo.read_text(ontology_id, version)
            for local_name, rdf_types in _TERM.findall(text):
                iri = f"{FORMAL_SEMANTIC_NAMESPACE}{local_name}"
                if "owl:Class" in rdf_types:
                    classes.add(iri)
                if any(
                    token in rdf_types
                    for token in ("owl:ObjectProperty", "owl:DatatypeProperty", "rdf:Property")
                ):
                    properties.add(iri)
        return cls(frozenset(classes), frozenset(properties))

    def require_class(self, iri: str) -> None:
        if iri not in self.classes:
            raise ValueError(f"class is not declared by the selected formal ontologies: {iri}")

    def require_property(self, iri: str) -> None:
        if iri not in self.properties:
            raise ValueError(f"property is not declared by the selected formal ontologies: {iri}")
