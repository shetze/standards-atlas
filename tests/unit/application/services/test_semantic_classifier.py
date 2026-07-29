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
