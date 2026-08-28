from dataclasses import dataclass

import pytest

from standards_atlas.application.semantic_classification import (
    SemanticClassificationContext,
    SemanticClassificationEngine,
    SemanticClassifierRegistry,
    SemanticDimensionResult,
    SemanticProfile,
)
from standards_atlas.application.semantic_ontology import OntologyDefinition, OntologyReference


class Definitions:
    def load(self, ontology_id: str, version: str) -> OntologyDefinition:
        return OntologyDefinition(
            id=ontology_id,
            version=version,
            dimension="knowledge_kinds",
            values=("process", "artifact"),
        )


@dataclass(frozen=True)
class Classifier:
    values: tuple[str, ...] = ("process",)

    @property
    def classifier_id(self) -> str:
        return "qualified-test"

    def classify(
        self,
        context: SemanticClassificationContext,
        definitions: dict[str, OntologyDefinition],
    ) -> tuple[SemanticDimensionResult, ...]:
        assert context.content == "verification process"
        assert definitions["knowledge_kinds"].id == "knowledge-kinds"
        return (SemanticDimensionResult("knowledge_kinds", self.values),)


def _profile() -> SemanticProfile:
    return SemanticProfile(
        id="functional-safety",
        version="1.0.0",
        dimensions={"knowledge_kinds": OntologyReference(id="knowledge-kinds", version="2.2.0")},
    )


def test_engine_composes_profile_and_classifier() -> None:
    engine = SemanticClassificationEngine(
        definitions=Definitions(),
        registry=SemanticClassifierRegistry((Classifier(),)),
    )

    result = engine.classify(
        profile=_profile(),
        classifier_id="qualified-test",
        context=SemanticClassificationContext(content="verification process"),
    )

    assert result == (SemanticDimensionResult("knowledge_kinds", ("process",)),)


def test_engine_rejects_values_outside_versioned_ontology() -> None:
    engine = SemanticClassificationEngine(
        definitions=Definitions(),
        registry=SemanticClassifierRegistry((Classifier(("unknown",)),)),
    )

    with pytest.raises(ValueError, match="undeclared values"):
        engine.classify(
            profile=_profile(),
            classifier_id="qualified-test",
            context=SemanticClassificationContext(content="verification process"),
        )
