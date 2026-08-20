from dataclasses import dataclass

import pytest

from standards_atlas.application.structure import (
    IecDirectives2Classifier,
    StructuralTaxonomyContext,
    StructuralTaxonomyDefinition,
    StructuralTaxonomyEngine,
    StructuralTaxonomyRegistry,
)


class _Definitions:
    def __init__(self, categories: frozenset[str]) -> None:
        self.categories = categories

    def load(self, taxonomy_id: str, version: str) -> StructuralTaxonomyDefinition:
        return StructuralTaxonomyDefinition(taxonomy_id, version, self.categories)


@dataclass(frozen=True)
class _Classifier:
    taxonomy_id: str = "document.test"
    taxonomy_version: str = "1.0.0"

    def classify(self, context: StructuralTaxonomyContext) -> tuple[str, ...]:
        return ("requirement",) if context.reference.startswith("REQ-") else ()


def test_engine_composes_generic_structure_with_replaceable_taxonomy() -> None:
    engine = StructuralTaxonomyEngine(
        StructuralTaxonomyRegistry((_Classifier(),)),
        definitions=_Definitions(frozenset({"requirement"})),
    )

    profile = engine.classify(
        StructuralTaxonomyContext(reference="REQ-42", heading="Safety requirement"),
        document_taxonomy=("document.test", "1.0.0"),
    )

    assert profile.canonical_section is None
    assert profile.document_categories[0].taxonomy == "document.test"
    assert profile.document_categories[0].category == "requirement"
    assert profile.document_categories[0].version == "1.0.0"


def test_registry_rejects_duplicate_versioned_classifier() -> None:
    registry = StructuralTaxonomyRegistry((_Classifier(),))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(_Classifier())


def test_engine_rejects_category_outside_taxonomy_contract() -> None:
    engine = StructuralTaxonomyEngine(
        StructuralTaxonomyRegistry((_Classifier(),)),
        definitions=_Definitions(frozenset({"module"})),
    )

    with pytest.raises(ValueError, match="undefined categories"):
        engine.classify(
            StructuralTaxonomyContext(reference="REQ-42", heading="Requirement"),
            document_taxonomy=("document.test", "1.0.0"),
        )


def test_iec_classifier_preserves_existing_document_categories() -> None:
    classifier = IecDirectives2Classifier()

    assert classifier.classify(StructuralTaxonomyContext("", "Foreword")) == (
        "preliminary_elements",
    )
    assert classifier.classify(StructuralTaxonomyContext("1", "Scope")) == (
        "normative_general_elements",
    )
    assert classifier.classify(StructuralTaxonomyContext("6.4", "Verification")) == (
        "normative_technical_elements",
    )
    assert classifier.classify(StructuralTaxonomyContext("A", "Annex A (normative)")) == (
        "supplementary_elements",
    )
    assert classifier.classify(StructuralTaxonomyContext("", "Bibliography")) == ("bibliography",)
