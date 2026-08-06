import pytest
from pydantic import ValidationError

from standards_atlas.application.semantic_qualification.annotations import (
    StatementFunctionSelection,
)
from standards_atlas.domain.model import (
    KnowledgeKind,
    SemanticClassification,
    StatementFunction,
)


def test_semantic_classification_accepts_orthogonal_knowledge_kinds() -> None:
    classification = SemanticClassification(
        knowledge_kinds=(KnowledgeKind.TECHNIQUE, KnowledgeKind.METHOD_OR_MEASURE)
    )
    assert classification.knowledge_kinds == (
        KnowledgeKind.TECHNIQUE,
        KnowledgeKind.METHOD_OR_MEASURE,
    )


def test_primary_knowledge_kind_must_be_selected() -> None:
    with pytest.raises(ValidationError):
        StatementFunctionSelection(primary_knowledge_kind=KnowledgeKind.METHOD_OR_MEASURE)


def test_condemnation_represents_negative_recommendation() -> None:
    classification = SemanticClassification(statement_functions=(StatementFunction.CONDEMNATION,))
    assert classification.statement_functions == (StatementFunction.CONDEMNATION,)


def test_warning_represents_adverse_risk_or_limitation() -> None:
    classification = SemanticClassification(statement_functions=(StatementFunction.WARNING,))
    assert classification.statement_functions == (StatementFunction.WARNING,)
