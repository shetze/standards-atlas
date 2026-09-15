"""Provider-neutral source-extraction vocabulary over packaged formal ontologies."""

from __future__ import annotations

from dataclasses import dataclass

from standards_atlas.application.formal_semantics import ResourceFormalOntologyRepository
from standards_atlas.domain.model import FORMAL_SEMANTIC_NAMESPACE


@dataclass(frozen=True)
class FormalOntologyVocabulary:
    """Closed engineering vocabulary explicitly exposed for source extraction."""

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
            definition = repo.load(ontology_id, version)
            classes.update(
                f"{FORMAL_SEMANTIC_NAMESPACE}{name}"
                for name in definition.extraction_vocabulary.classes
            )
            properties.update(
                f"{FORMAL_SEMANTIC_NAMESPACE}{name}"
                for name in definition.extraction_vocabulary.properties
            )
        return cls(frozenset(classes), frozenset(properties))

    def require_class(self, iri: str) -> None:
        if iri not in self.classes:
            raise ValueError(f"class is not source-extractable in the selected ontologies: {iri}")

    def require_property(self, iri: str) -> None:
        if iri not in self.properties:
            raise ValueError(
                f"property is not source-extractable in the selected ontologies: {iri}"
            )
