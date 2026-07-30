from standards_atlas.application.services.semantic_classifier import (
    SemanticClassificationContext,
    SemanticClassifier,
)
from standards_atlas.domain.model import (
    DocumentStructure,
    NormativeStatus,
    StatementFunction,
)


def test_classifier_separates_statement_structure_status_and_domain():
    result = SemanticClassifier().classify(
        SemanticClassificationContext(
            reference="A.2",
            heading="Annex A — Software verification",
            text="The software shall be verified.",
            knowledge_domain="functional-safety",
            annex_status=NormativeStatus.NORMATIVE,
        )
    )

    classification = result.classification
    assert classification.statement_functions == (StatementFunction.REQUIREMENT,)
    assert classification.document_structure.category is DocumentStructure.ANNEX
    assert classification.normative_status is NormativeStatus.NORMATIVE
    assert classification.domain_functions[0].functions == ("verification",)


def test_main_body_defaults_to_normative() -> None:
    result = SemanticClassifier().classify(
        SemanticClassificationContext(reference="5.3.1", heading="General requirements")
    )

    assert result.classification.normative_status is NormativeStatus.NORMATIVE


def test_informative_annex_status_is_detected_from_heading() -> None:
    result = SemanticClassifier().classify(
        SemanticClassificationContext(
            reference="A",
            heading="Annex A (informative) — Examples",
        )
    )

    assert result.classification.normative_status is NormativeStatus.INFORMATIVE


def test_annex_without_status_remains_unspecified() -> None:
    result = SemanticClassifier().classify(
        SemanticClassificationContext(reference="A.1", heading="Examples")
    )

    assert result.classification.normative_status is NormativeStatus.UNSPECIFIED


def test_bibliography_defaults_to_informative() -> None:
    result = SemanticClassifier().classify(
        SemanticClassificationContext(reference="", heading="Bibliography")
    )

    assert result.classification.normative_status is NormativeStatus.INFORMATIVE
