from dataclasses import dataclass

import pytest

from standards_atlas.application.ontology import (
    OntologyContext,
    OntologyDefinition,
    OntologyDimensionResult,
    OntologyEngine,
    OntologyProfile,
    OntologyReference,
    OntologyRegistry,
)


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
        context: OntologyContext,
        definitions: dict[str, OntologyDefinition],
    ) -> tuple[OntologyDimensionResult, ...]:
        assert context.content == "verification process"
        assert definitions["knowledge_kinds"].id == "knowledge-kinds"
        return (OntologyDimensionResult("knowledge_kinds", self.values),)


def _profile() -> OntologyProfile:
    return OntologyProfile(
        id="functional-safety",
        dimensions={"knowledge_kinds": OntologyReference(id="knowledge-kinds", version="2.2.0")},
    )


def test_engine_composes_profile_and_classifier() -> None:
    engine = OntologyEngine(
        definitions=Definitions(),
        registry=OntologyRegistry((Classifier(),)),
    )

    result = engine.classify(
        profile=_profile(),
        classifier_id="qualified-test",
        context=OntologyContext(content="verification process"),
    )

    assert result == (OntologyDimensionResult("knowledge_kinds", ("process",)),)


def test_engine_rejects_values_outside_versioned_ontology() -> None:
    engine = OntologyEngine(
        definitions=Definitions(),
        registry=OntologyRegistry((Classifier(("unknown",)),)),
    )

    with pytest.raises(ValueError, match="undeclared values"):
        engine.classify(
            profile=_profile(),
            classifier_id="qualified-test",
            context=OntologyContext(content="verification process"),
        )
