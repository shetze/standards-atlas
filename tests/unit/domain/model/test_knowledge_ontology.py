import pytest
from pydantic import ValidationError

from standards_atlas.application.semantic_qualification.annotations import (
    StatementFunctionSelection,
)
from standards_atlas.domain.model import KnowledgeKind, SemanticClassification


def test_semantic_classification_accepts_orthogonal_knowledge_kinds() -> None:
    classification = SemanticClassification(
        knowledge_kinds=(KnowledgeKind.TECHNIQUE, KnowledgeKind.MEASURE)
    )
    assert classification.knowledge_kinds == (
        KnowledgeKind.TECHNIQUE,
        KnowledgeKind.MEASURE,
    )


def test_primary_knowledge_kind_must_be_selected() -> None:
    with pytest.raises(ValidationError):
        StatementFunctionSelection(primary_knowledge_kind=KnowledgeKind.METHOD)
