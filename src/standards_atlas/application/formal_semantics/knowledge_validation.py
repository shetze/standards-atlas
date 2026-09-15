"""Validation of accepted document knowledge against packaged formal ontologies."""

from __future__ import annotations

from standards_atlas.domain.model import DocumentKnowledge

from .resource_repository import ResourceFormalOntologyRepository


class DocumentKnowledgeOntologyValidator:
    """Require canonical knowledge terms to exist in its bound ontology versions."""

    def __init__(self, repository: ResourceFormalOntologyRepository | None = None) -> None:
        self._repository = repository or ResourceFormalOntologyRepository()

    def validate(self, knowledge: DocumentKnowledge) -> None:
        classes: set[str] = set()
        properties: set[str] = set()
        for reference in knowledge.ontology_versions:
            ontology_id, version = reference.rsplit("@", 1)
            vocabulary = self._repository.declared_vocabulary(ontology_id, version)
            classes.update(vocabulary.classes)
            properties.update(vocabulary.properties)

        missing_classes = sorted(
            {entity.class_iri for entity in knowledge.entities if entity.class_iri not in classes}
        )
        missing_properties = sorted(
            {
                assertion.predicate
                for assertion in knowledge.assertions
                if assertion.predicate not in properties
            }
        )
        if not missing_classes and not missing_properties:
            return

        details: list[str] = []
        if missing_classes:
            details.append(f"classes={missing_classes!r}")
        if missing_properties:
            details.append(f"properties={missing_properties!r}")
        raise ValueError(
            "document knowledge uses terms not declared by its selected formal ontologies: "
            + ", ".join(details)
        )
