from standards_atlas.application.services.semantic_classifier import (
    SemanticClassificationContext,
    SemanticClassifier,
)
from standards_atlas.domain.model import (
    DocumentStructure,
    NormativeStatus,
    ProcessFunction,
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


def test_main_standard_body_defaults_to_normative():
    result = SemanticClassifier().classify(
        SemanticClassificationContext(reference="5.1", heading="General")
    )
    assert result.classification.normative_status is NormativeStatus.NORMATIVE


def test_note_example_and_guideline_are_informative():
    classifier = SemanticClassifier()
    cases = (
        ("NOTE: This explains the requirement.", StatementFunction.NOTE),
        ("EXAMPLE 1: A possible implementation.", StatementFunction.EXAMPLE),
        ("Guidelines for verification", StatementFunction.GUIDELINE),
    )
    for text, function in cases:
        result = classifier.classify(
            SemanticClassificationContext(reference="5.1", heading=text, text=text)
        )
        assert function in result.classification.statement_functions
        assert result.classification.normative_status is NormativeStatus.INFORMATIVE


def test_guidelines_document_is_informative_by_default():
    result = SemanticClassifier().classify(
        SemanticClassificationContext(
            reference="5.1",
            heading="General",
            document_title="ISO 26262-10, Guidelines on ISO 26262",
        )
    )
    assert result.classification.normative_status is NormativeStatus.INFORMATIVE


def test_annex_status_is_inherited_from_context():
    result = SemanticClassifier().classify(
        SemanticClassificationContext(
            reference="A.2.1",
            heading="Example calculation",
            annex_status=NormativeStatus.INFORMATIVE,
        )
    )
    assert result.classification.normative_status is NormativeStatus.INFORMATIVE


def test_classifier_detects_process_semantics() -> None:
    result = SemanticClassifier().classify_deterministically(
        SemanticClassificationContext(
            reference="6.4",
            heading="Prerequisites",
            text="Before the activity, the safety plan shall be available as an input.",
        )
    )

    assert ProcessFunction.PREREQUISITE in result.classification.process_functions
    assert ProcessFunction.SEQUENCE in result.classification.process_functions
    assert ProcessFunction.INPUT in result.classification.process_functions
