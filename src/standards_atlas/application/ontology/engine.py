"""Application contracts for modular ontology classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from standards_atlas.application.ontology.definition import (
    OntologyDefinition,
    OntologyDefinitionRepository,
    OntologyProfile,
)


@dataclass(frozen=True)
class OntologyContext:
    """Input shared by ontology classifiers.

    Slice 1 intentionally keeps the context generic. Later workflow slices will supply
    the taxonomically derived structural context explicitly.
    """

    content: str
    structural_context: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OntologyDimensionResult:
    """Classification result for one ontology dimension."""

    dimension: str
    values: tuple[str, ...]


class OntologyClassifier(Protocol):
    """Interchangeable classifier for a composed ontology profile."""

    @property
    def classifier_id(self) -> str: ...

    def classify(
        self,
        context: OntologyContext,
        definitions: dict[str, OntologyDefinition],
    ) -> tuple[OntologyDimensionResult, ...]: ...


class OntologyRegistry:
    """Resolve ontology classifiers by stable classifier id."""

    def __init__(self, classifiers: tuple[OntologyClassifier, ...] = ()) -> None:
        self._classifiers: dict[str, OntologyClassifier] = {}
        for classifier in classifiers:
            self.register(classifier)

    def register(self, classifier: OntologyClassifier) -> None:
        if classifier.classifier_id in self._classifiers:
            raise ValueError(f"duplicate ontology classifier: {classifier.classifier_id}")
        self._classifiers[classifier.classifier_id] = classifier

    def resolve(self, classifier_id: str) -> OntologyClassifier:
        try:
            return self._classifiers[classifier_id]
        except KeyError as exc:
            raise KeyError(f"unknown ontology classifier: {classifier_id}") from exc


class OntologyEngine:
    """Compose ontology definitions with an interchangeable classifier."""

    def __init__(
        self,
        *,
        definitions: OntologyDefinitionRepository,
        registry: OntologyRegistry,
    ) -> None:
        self._definitions = definitions
        self._registry = registry

    def classify(
        self,
        *,
        profile: OntologyProfile,
        classifier_id: str,
        context: OntologyContext,
    ) -> tuple[OntologyDimensionResult, ...]:
        definitions = {
            dimension: self._definitions.load(reference.id, reference.version)
            for dimension, reference in profile.dimensions.items()
        }
        mismatches = [
            f"{dimension}->{definition.dimension}"
            for dimension, definition in definitions.items()
            if dimension != definition.dimension
        ]
        if mismatches:
            raise ValueError("ontology profile dimension mismatch: " + ", ".join(mismatches))

        classifier = self._registry.resolve(classifier_id)
        results = classifier.classify(context, definitions)
        self._validate_results(definitions, results)
        return results

    @staticmethod
    def _validate_results(
        definitions: dict[str, OntologyDefinition],
        results: tuple[OntologyDimensionResult, ...],
    ) -> None:
        seen: set[str] = set()
        for result in results:
            if result.dimension in seen:
                raise ValueError(f"duplicate ontology result dimension: {result.dimension}")
            seen.add(result.dimension)
            try:
                definition = definitions[result.dimension]
            except KeyError as exc:
                raise ValueError(
                    f"ontology classifier emitted unconfigured dimension: {result.dimension}"
                ) from exc
            invalid = sorted(set(result.values) - set(definition.values))
            if invalid:
                raise ValueError(
                    f"ontology classifier emitted undeclared values for {result.dimension}: "
                    + ", ".join(invalid)
                )
