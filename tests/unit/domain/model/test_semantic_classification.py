import pytest
from pydantic import ValidationError

from standards_atlas.domain.model import (
    ApplicabilityFunction,
    DocumentStructure,
    DocumentStructureClassification,
    DomainFunctionClassification,
    NormativeStatus,
    ProcessFunction,
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


def test_semantic_classification_supports_process_functions() -> None:
    classification = SemanticClassification(
        statement_functions=(StatementFunction.REQUIREMENT,),
        process_functions=(ProcessFunction.PREREQUISITE, ProcessFunction.INPUT),
    )

    assert classification.process_functions == (
        ProcessFunction.PREREQUISITE,
        ProcessFunction.INPUT,
    )


def test_role_semantics_can_be_present_without_extractable_relation() -> None:
    classification = SemanticClassification(role_semantics_present=True)

    assert classification.role_semantics_present is True
    assert classification.role_relations == ()


def test_role_relations_support_multiple_grounded_tuples() -> None:
    from standards_atlas.domain.model import RoleRelation

    classification = SemanticClassification(
        role_semantics_present=True,
        role_relations=(
            RoleRelation(
                actor="Validator",
                relation_class="performance",
                target="system",
            ),
            RoleRelation(
                actor="Validator",
                relation_class="dependency",
                target="Designer",
            ),
        ),
    )

    assert len(classification.role_relations) == 2
    assert classification.role_relations[0].actor == "Validator"
    assert classification.role_relations[0].relation_class == "performance"
    assert classification.role_relations[1].relation_class == "dependency"


def test_role_relation_supports_open_class_and_target() -> None:
    from standards_atlas.domain.model import RoleRelation

    relation = RoleRelation(
        actor="Assessor",
        relation_class="performance",
        target="deviations",
    )

    assert relation.relation_class == "performance"
    assert relation.target == "deviations"


def test_role_relations_require_explicit_role_semantics_when_presence_is_supplied() -> None:
    from standards_atlas.domain.model import RoleRelation

    with pytest.raises(ValidationError, match="role relation classifications require"):
        SemanticClassification(
            role_semantics_present=False,
            role_relations=(
                RoleRelation(
                    actor="Verifier",
                    relation_class="performance",
                    target="verification evidence",
                ),
            ),
        )


def test_applicability_presence_can_be_true_without_subtype() -> None:
    classification = SemanticClassification(applicability_present=True)

    assert classification.applicability_present is True
    assert classification.applicability_functions == ()


def test_applicability_subtype_requires_presence() -> None:
    with pytest.raises(ValueError, match="applicability functions require"):
        SemanticClassification(
            applicability_present=False, applicability_functions=(ApplicabilityFunction.INCLUSION,)
        )
