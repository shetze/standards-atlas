"""Sparse canonical values carry availability, never fabricated companions."""

import pytest
from test_enrichment_patch import clause, merge

from standards_atlas.application.context.canonical_cbox import project_clause_enrichments
from standards_atlas.domain.model import Clause, SemanticClassification
from standards_atlas.domain.model.enrichment_patch import (
    ClauseEnrichmentPatch,
    SemanticEnrichmentPatch,
    merge_generated_enrichments,
)
from standards_atlas.domain.model.knowledge_state import GeneratedAttribute, GenerationMethod

PREFIX = "enrichments.semantic."
PAIRS = [
    ("primary_function", "statement_functions", "definition", "description"),
    ("primary_knowledge_kind", "knowledge_kinds", "process", "concept"),
    ("primary_process_function", "process_functions", "activity", "output"),
]


def sparse(current, *, values=None, unknown=()):
    values = values or {}
    attrs = tuple(
        GeneratedAttribute(
            path=PREFIX + field,
            generator="taxonomy-partial-adoption-v1",
            method=GenerationMethod.LLM,
        )
        for field in values
    )
    attrs += tuple(
        GeneratedAttribute(
            path=PREFIX + field,
            generator="taxonomy-partial-adoption-v1",
            method=GenerationMethod.LLM,
            availability="unknown",
        )
        for field in unknown
    )
    return merge_generated_enrichments(
        current, ClauseEnrichmentPatch(semantic=SemanticEnrichmentPatch(**values)), attrs
    )


@pytest.mark.parametrize("primary,members,value,other", PAIRS)
def test_known_primary_with_unobserved_empty_set_survives_json_and_cbox(
    primary, members, value, other
):
    result = sparse(clause(), values={primary: value}).clause
    assert getattr(result.semantic_classification, members) == ()
    assert result.provenance.availability(PREFIX + members) == "not_evaluated"
    restored = Clause.model_validate_json(result.model_dump_json())
    assert restored == result
    fields = {item.path: item for item in project_clause_enrichments(restored).attributes}
    assert fields[PREFIX + primary].value == value
    assert fields[PREFIX + members].value is None
    assert fields[PREFIX + members].availability == "not_evaluated"


@pytest.mark.parametrize("primary,members,value,other", PAIRS)
def test_known_empty_set_is_not_weakened_to_an_unobserved_set(primary, members, value, other):
    with pytest.raises(ValueError):
        sparse(clause(), values={primary: value, members: ()})
    with pytest.raises(ValueError):
        SemanticClassification(**{primary: value})


@pytest.mark.parametrize("primary,members,value,other", PAIRS)
def test_new_primary_invalidates_stale_unprotected_set_without_inventing_members(
    primary, members, value, other
):
    previous = merge(clause(), **{members: (other,), primary: other}).clause
    result = sparse(previous, values={primary: value}).clause
    assert getattr(result.semantic_classification, primary) == value
    assert getattr(result.semantic_classification, members) == ()
    assert result.provenance.availability(PREFIX + members) == "unknown"
    assert Clause.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("primary,members,value,other", PAIRS)
@pytest.mark.parametrize("empty", [True, False])
def test_confirmed_companion_blocks_incompatible_new_primary_even_when_empty(
    primary, members, value, other, empty
):
    previous = merge(clause(), **{members: () if empty else (other,)}).clause
    previous = previous.confirm_authoritative(PREFIX + members)
    result = sparse(previous, values={primary: value, "applicability_present": True})
    assert getattr(result.clause.semantic_classification, primary) is None
    assert result.clause.provenance.protection(PREFIX + members) == "confirmed"
    assert result.clause.semantic_classification.applicability_present is True
    assert any(c.status == "protected" for c in result.changes)


def test_unknown_presence_does_not_erase_known_relations_or_infer_true():
    relation = {"actor": "supplier", "relation_class": "responsibility", "target": "review"}
    result = sparse(
        clause(), values={"role_relations": [relation]}, unknown=("role_semantics_present",)
    ).clause
    assert len(result.semantic_classification.role_relations) == 1
    assert result.provenance.availability(PREFIX + "role_semantics_present") == "unknown"
    assert Clause.model_validate_json(result.model_dump_json()) == result
    presence = next(
        a
        for a in project_clause_enrichments(result).attributes
        if a.path.endswith("role_semantics_present")
    )
    assert presence.value is None


def test_evaluated_negative_presence_still_rejects_nonempty_relations():
    relation = {"actor": "supplier", "relation_class": "responsibility", "target": "review"}
    with pytest.raises(ValueError):
        sparse(clause(), values={"role_relations": [relation], "role_semantics_present": False})


def test_negative_sparse_presence_does_not_manufacture_unasked_empty_dependencies():
    result = sparse(
        clause(), values={"applicability_present": False, "role_semantics_present": False}
    ).clause
    for name in ("applicability_functions", "role_relations", "role_relation_types"):
        assert result.provenance.availability(PREFIX + name) == "not_evaluated"


def test_unknown_candidate_preserves_previous_known_value_and_authority():
    previous = merge(clause(), applicability_present=True).clause
    assert sparse(previous, unknown=("applicability_present",)).clause == previous
    previous = previous.confirm_authoritative(PREFIX + "applicability_present")
    assert sparse(previous, values={"applicability_present": False}).clause == previous
