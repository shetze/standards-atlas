import pytest
from pydantic import ValidationError

from standards_atlas.domain.model import (
    DocumentStructure,
    DocumentStructureClassification,
    DomainFunctionClassification,
    NormativeStatus,
    RelationScope,
    SemanticClassification,
    SemanticRelation,
    SemanticRelationKind,
    StatementFunction,
)


def test_semantic_dimensions_are_independent():
    classification = SemanticClassification(
        statement_functions=(StatementFunction.REQUIREMENT,),
        document_structure=DocumentStructureClassification(
            family="iso_iec_standard", category=DocumentStructure.ANNEX, annex_identifier="A"
        ),
        normative_status=NormativeStatus.NORMATIVE,
        domain_functions=(
            DomainFunctionClassification(
                knowledge_domain="functional-safety",
                taxonomy_version="1.0.0",
                functions=("verification",),
            ),
        ),
    )

    assert classification.statement_functions == (StatementFunction.REQUIREMENT,)
    assert classification.document_structure.category is DocumentStructure.ANNEX
    assert classification.normative_status is NormativeStatus.NORMATIVE
    assert classification.domain_functions[0].functions == ("verification",)


def test_external_relation_requires_target_document():
    with pytest.raises(ValidationError):
        SemanticRelation(
            kind=SemanticRelationKind.REFERENCES,
            scope=RelationScope.EXTERNAL,
            target_reference="4.2",
        )
