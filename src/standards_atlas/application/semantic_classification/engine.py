"""Application contracts for modular semantic classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from standards_atlas.application.semantic_classification.profile import SemanticProfile
from standards_atlas.application.semantic_ontology.definition import (
    OntologyDefinition,
    OntologyDefinitionRepository,
)


@dataclass(frozen=True)
class SemanticClassificationContext:
    """Input shared by semantic classifiers.

    Slice 1 intentionally keeps the context generic. Later workflow slices will supply
    the taxonomically derived structural context explicitly.
    """

    content: str
    structural_context: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticDimensionResult:
    """Classification result for one semantic profile dimension.

    ``presence`` is used for dimensions whose existence is decided independently
    from their subtype labels (currently applicability). Keeping it on the
    dimension result lets production classification preserve the qualified task
    contract instead of inferring presence from a non-empty subtype list.
    """

    dimension: str
    values: tuple[str, ...]
    presence: bool | None = None


class SemanticClassifier(Protocol):
    """Interchangeable classifier for a composed semantic profile."""

    @property
    def classifier_id(self) -> str: ...

    def classify(
        self,
        context: SemanticClassificationContext,
        definitions: dict[str, OntologyDefinition],
    ) -> tuple[SemanticDimensionResult, ...]: ...


class SemanticClassifierRegistry:
    """Resolve semantic classifiers by stable classifier id."""

    def __init__(self, classifiers: tuple[SemanticClassifier, ...] = ()) -> None:
        self._classifiers: dict[str, SemanticClassifier] = {}
        for classifier in classifiers:
            self.register(classifier)

    def register(self, classifier: SemanticClassifier) -> None:
        if classifier.classifier_id in self._classifiers:
            raise ValueError(f"duplicate semantic classifier: {classifier.classifier_id}")
        self._classifiers[classifier.classifier_id] = classifier

    def resolve(self, classifier_id: str) -> SemanticClassifier:
        try:
            return self._classifiers[classifier_id]
        except KeyError as exc:
            raise KeyError(f"unknown semantic classifier: {classifier_id}") from exc


class SemanticClassificationEngine:
    """Classify a semantic profile using its referenced ontology definitions."""

    def __init__(
        self,
        *,
        definitions: OntologyDefinitionRepository,
        registry: SemanticClassifierRegistry,
    ) -> None:
        self._definitions = definitions
        self._registry = registry

    def classify(
        self,
        *,
        profile: SemanticProfile,
        classifier_id: str,
        context: SemanticClassificationContext,
    ) -> tuple[SemanticDimensionResult, ...]:
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
            raise ValueError("semantic profile dimension mismatch: " + ", ".join(mismatches))

        classifier = self._registry.resolve(classifier_id)
        results = classifier.classify(context, definitions)
        self._validate_results(definitions, results)
        return results

    @staticmethod
    def _validate_results(
        definitions: dict[str, OntologyDefinition],
        results: tuple[SemanticDimensionResult, ...],
    ) -> None:
        seen: set[str] = set()
        for result in results:
            if result.dimension in seen:
                raise ValueError(f"duplicate semantic result dimension: {result.dimension}")
            seen.add(result.dimension)
            try:
                definition = definitions[result.dimension]
            except KeyError as exc:
                raise ValueError(
                    f"semantic classifier emitted unconfigured dimension: {result.dimension}"
                ) from exc
            invalid = sorted(set(result.values) - set(definition.values))
            if invalid:
                raise ValueError(
                    f"semantic classifier emitted undeclared values for {result.dimension}: "
                    + ", ".join(invalid)
                )
