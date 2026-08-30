import pytest
from pydantic import ValidationError

from standards_atlas.domain.model import (
    ContextRouting,
    ReferenceRole,
    ReferenceRouting,
    ReferenceTarget,
    ScopeDeclaration,
    ScopeReach,
    ScopeReachKind,
)


def test_models_document_scope_reach():
    reach = ScopeReach(kind=ScopeReachKind.DOCUMENT, document_key="ISO26262-5")

    assert reach.kind is ScopeReachKind.DOCUMENT
    assert reach.document_key == "ISO26262-5"


def test_models_part_scope_reach():
    reach = ScopeReach(
        kind=ScopeReachKind.PART,
        document_key="IEC61508",
        part="3",
    )

    assert reach.kind is ScopeReachKind.PART
    assert reach.part == "3"


def test_models_subtree_scope_reach_by_clause_reference():
    reach = ScopeReach(kind=ScopeReachKind.SUBTREE, reference="7.4")

    assert reach.kind is ScopeReachKind.SUBTREE
    assert reach.reference == "7.4"


def test_models_single_clause_scope_reach_by_resolved_clause_id():
    reach = ScopeReach(kind=ScopeReachKind.CLAUSE, clause_id="clause-abc")

    assert reach.kind is ScopeReachKind.CLAUSE
    assert reach.clause_id == "clause-abc"


def test_rejects_part_scope_without_part():
    with pytest.raises(ValidationError, match="part scope reach requires part"):
        ScopeReach(kind=ScopeReachKind.PART)


def test_rejects_clause_scope_without_clause_address():
    with pytest.raises(ValidationError, match="clause scope reach requires"):
        ScopeReach(kind=ScopeReachKind.CLAUSE)


def test_scope_declaration_keeps_meta_level_conditions_separate_from_reach():
    declaration = ScopeDeclaration(
        source_clause_id="scope-1",
        reaches=(ScopeReach(kind=ScopeReachKind.SUBTREE, reference="7"),),
        conditions=("applies to programmable electronic systems",),
        exclusions=("does not apply to external measures",),
        qualifications=("unless otherwise specified",),
        evidence=("scope-1:text",),
    )

    assert declaration.reaches[0].reference == "7"
    assert declaration.conditions == ("applies to programmable electronic systems",)
    assert declaration.exclusions == ("does not apply to external measures",)


def test_reference_routing_adds_role_without_changing_syntactic_target():
    routing = ReferenceRouting(
        source_clause_id="clause-8",
        target=ReferenceTarget(
            document_key="ISO26262-5",
            clause_id="clause-7",
            reference="7.4",
            title="Hardware architectural metrics",
        ),
        role=ReferenceRole.PROVIDES_PROCEDURE,
        evidence=("reference-mention:0",),
    )

    assert routing.role is ReferenceRole.PROVIDES_PROCEDURE
    assert routing.target.reference == "7.4"
    assert routing.target.clause_id == "clause-7"


def test_context_routing_combines_scope_and_reference_routes():
    context = ContextRouting(
        scopes=(
            ScopeDeclaration(
                source_clause_id="scope-1",
                reaches=(ScopeReach(kind=ScopeReachKind.DOCUMENT),),
            ),
        ),
        references=(
            ReferenceRouting(
                source_clause_id="scope-1",
                target=ReferenceTarget(reference="IEC 61508-2:2010, 7.4"),
                role=ReferenceRole.PROVIDES_APPLICABILITY,
            ),
        ),
    )

    assert context.scopes[0].reaches[0].kind is ScopeReachKind.DOCUMENT
    assert context.references[0].role is ReferenceRole.PROVIDES_APPLICABILITY
