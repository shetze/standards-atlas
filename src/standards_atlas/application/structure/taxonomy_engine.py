"""Deterministic, replaceable structural-taxonomy classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from standards_atlas.application.services.structural_profile_classifier import (
    StructuralProfileClassifier,
    StructuralProfileContext,
)
from standards_atlas.application.structure.taxonomy_definition import (
    StructuralTaxonomyDefinitionRepository,
)
from standards_atlas.domain.model.structural_profile import DomainCategory, StructuralProfile


@dataclass(frozen=True)
class StructuralTaxonomyContext:
    """Tree/text evidence exposed to one deterministic taxonomy classifier."""

    reference: str
    heading: str
    text: str = ""


class StructuralTaxonomyClassifier(Protocol):
    """Algorithm plug-in for one versioned structural taxonomy."""

    @property
    def taxonomy_id(self) -> str: ...

    @property
    def taxonomy_version(self) -> str: ...

    def classify(self, context: StructuralTaxonomyContext) -> tuple[str, ...]:
        """Return zero or more category identifiers owned by the taxonomy."""
        ...


class StructuralTaxonomyRegistry:
    """Registry of deterministic classifiers keyed by versioned taxonomy id."""

    def __init__(self, classifiers: tuple[StructuralTaxonomyClassifier, ...] = ()) -> None:
        self._classifiers: dict[tuple[str, str], StructuralTaxonomyClassifier] = {}
        for classifier in classifiers:
            self.register(classifier)

    def register(self, classifier: StructuralTaxonomyClassifier) -> None:
        key = (classifier.taxonomy_id, classifier.taxonomy_version)
        if key in self._classifiers:
            raise ValueError(
                "structural taxonomy classifier already registered: "
                f"{classifier.taxonomy_id}@{classifier.taxonomy_version}"
            )
        self._classifiers[key] = classifier

    def resolve(self, taxonomy_id: str, version: str) -> StructuralTaxonomyClassifier:
        try:
            return self._classifiers[(taxonomy_id, version)]
        except KeyError as exc:
            raise KeyError(
                f"no structural taxonomy classifier registered for {taxonomy_id}@{version}"
            ) from exc


class StructuralTaxonomyEngine:
    """Compose generic structural analysis with selected taxonomy plug-ins."""

    def __init__(
        self,
        registry: StructuralTaxonomyRegistry,
        *,
        base_classifier: StructuralProfileClassifier | None = None,
        definitions: StructuralTaxonomyDefinitionRepository | None = None,
    ) -> None:
        self._registry = registry
        self._base_classifier = base_classifier or StructuralProfileClassifier()
        self._definitions = definitions

    def classify(
        self,
        context: StructuralTaxonomyContext,
        *,
        document_taxonomy: tuple[str, str] | None = None,
        domain_taxonomies: tuple[tuple[str, str], ...] = (),
    ) -> StructuralProfile:
        """Classify generic structure and explicitly selected taxonomy dimensions."""

        base = self._base_classifier.classify(
            StructuralProfileContext(
                reference=context.reference,
                heading=context.heading,
                text=context.text,
            )
        )
        document_categories = self._assign(context, document_taxonomy)
        domain_categories = tuple(
            assignment
            for taxonomy in domain_taxonomies
            for assignment in self._assign(context, taxonomy)
        )
        return base.model_copy(
            update={
                "document_categories": document_categories,
                "domain_categories": domain_categories,
            }
        )

    def _assign(
        self,
        context: StructuralTaxonomyContext,
        taxonomy: tuple[str, str] | None,
    ) -> tuple[DomainCategory, ...]:
        if taxonomy is None:
            return ()
        taxonomy_id, version = taxonomy
        classifier = self._registry.resolve(taxonomy_id, version)
        categories = classifier.classify(context)
        if self._definitions is not None:
            definition = self._definitions.load(taxonomy_id, version)
            unknown = tuple(
                category for category in categories if category not in definition.categories
            )
            if unknown:
                raise ValueError(
                    f"classifier {taxonomy_id}@{version} emitted undefined categories: "
                    + ", ".join(unknown)
                )
        return tuple(
            DomainCategory(
                taxonomy=taxonomy_id,
                category=category,
                version=version,
            )
            for category in categories
        )
