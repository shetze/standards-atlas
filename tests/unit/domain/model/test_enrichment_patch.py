"""Regression coverage for availability and authority-aware partial updates."""

import pytest

from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    GeneratedAttribute,
    GenerationMethod,
    SemanticClassification,
    StandardReference,
)
from standards_atlas.domain.model.enrichment_patch import (
    ClauseEnrichmentPatch,
    SemanticEnrichmentPatch,
    merge_generated_enrichments,
)
from standards_atlas.domain.model.knowledge_state import DecisionSupport


def clause(**semantic):
    return Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="TEST", clause="1"),
        clause_type=ClauseType.CLAUSE,
        semantic_classification=SemanticClassification(**semantic),
    )


def merge(current, **values):
    patch = ClauseEnrichmentPatch(semantic=SemanticEnrichmentPatch(**values))
    attrs = tuple(
        GeneratedAttribute(
            path=f"enrichments.semantic.{field}",
            generator="test",
            method=GenerationMethod.IMPORTED,
        )
        for field in values
    )
    return merge_generated_enrichments(current, patch, attrs)


def test_false_empty_and_unassessed_have_distinct_availability():
    original = clause()
    updated = merge(original, applicability_present=False, process_functions=()).clause
    assert updated.semantic_classification.applicability_present is False
    assert updated.provenance.availability("enrichments.semantic.applicability_present") == "known"
    assert updated.provenance.availability("enrichments.semantic.process_functions") == "known"
    assert (
        original.provenance.availability("enrichments.semantic.applicability_present")
        == "not_evaluated"
    )
    assert (
        updated.provenance.availability("enrichments.semantic.role_semantics_present")
        == "not_evaluated"
    )


def test_presence_without_details_roundtrips_canonical_model():
    result = merge(clause(), applicability_present=True, role_semantics_present=True).clause
    assert Clause.model_validate_json(result.model_dump_json()) == result
    assert result.semantic_classification.applicability_functions == ()
    assert result.semantic_classification.role_relations == ()


def test_negative_presence_clears_stale_details_but_not_other_dimensions():
    current = clause(
        applicability_present=True,
        applicability_functions=("inclusion",),
        knowledge_kinds=("process",),
    )
    result = merge(current, applicability_present=False).clause
    assert result.semantic_classification.applicability_functions == ()
    assert result.semantic_classification.knowledge_kinds == ("process",)


def test_authoritative_false_blocks_positive_even_with_no_generated_marker():
    current = clause().confirm_authoritative("enrichments.semantic.applicability_present")
    result = merge(current, applicability_present=True, knowledge_kinds=("process",))
    assert result.clause.semantic_classification.applicability_present is False
    assert result.clause.semantic_classification.knowledge_kinds == ("process",)
    assert any(change.status == "protected" for change in result.changes)
    assert (
        result.clause.provenance.protection("enrichments.semantic.applicability_present")
        == "confirmed"
    )


def test_confirmed_detail_blocks_incompatible_presence_as_one_group():
    current = clause(applicability_present=True, applicability_functions=("inclusion",))
    current = current.confirm_authoritative("enrichments.semantic.applicability_functions")
    result = merge(current, applicability_present=False)
    assert result.clause == current
    assert all(change.status == "protected" for change in result.changes)


def test_identical_confirmed_value_does_not_become_generated():
    current = clause(applicability_present=True).confirm_authoritative(
        "enrichments.semantic.applicability_present",
        authority="atlasdata",
    )
    result = merge(current, applicability_present=True)
    assert result.clause == current
    assert result.changes[0].status == "unchanged"


def test_parent_confirmation_protects_child_updates():
    current = clause().confirm_authoritative("enrichments.semantic")
    assert merge(current, statement_functions=("description",)).clause == current


def test_unknown_assessment_preserves_a_known_value():
    current = merge(clause(), applicability_present=True).clause
    unknown = GeneratedAttribute(
        path="enrichments.semantic.applicability_present",
        generator="test2",
        method=GenerationMethod.IMPORTED,
        availability="unknown",
    )
    result = merge_generated_enrichments(current, ClauseEnrichmentPatch(), (unknown,))
    assert result.clause == current
    empty = merge_generated_enrichments(clause(), ClauseEnrichmentPatch(), (unknown,)).clause
    assert empty.provenance.availability(unknown.path) == "unknown"
    assert empty.semantic_classification.applicability_present is False  # storage default only


def test_replay_is_idempotent():
    first = merge(clause(), primary_function="description", statement_functions=("description",))
    second = merge(
        first.clause,
        primary_function="description",
        statement_functions=("description",),
    )
    assert second.clause == first.clause
    assert {item.status for item in second.changes} == {"unchanged"}


def test_patch_requires_provenance_and_consistent_coupled_values():
    with pytest.raises(ValueError, match="provenance"):
        merge_generated_enrichments(
            clause(),
            ClauseEnrichmentPatch(semantic=SemanticEnrichmentPatch(applicability_present=True)),
            (),
        )
    with pytest.raises(ValueError, match="negative presence"):
        merge(clause(), applicability_present=False, applicability_functions=("inclusion",))


def test_primary_is_not_inferred_from_a_secondary_only_set():
    updated = merge(clause(), statement_functions=("description",)).clause
    assert updated.semantic_classification.primary_function is None
    assert (
        updated.provenance.availability("enrichments.semantic.primary_function") == "not_evaluated"
    )


def test_stale_primary_is_cleared_when_replacing_its_set():
    current = clause(primary_function="description", statement_functions=("description",))
    updated = merge(current, statement_functions=("requirement",)).clause
    assert updated.semantic_classification.primary_function is None
    assert updated.semantic_classification.statement_functions == ("requirement",)


def test_vote_support_is_validated_not_treated_as_model_probability():
    with pytest.raises(ValueError, match="exceed"):
        DecisionSupport(
            rule="vote",
            source_artifact="source",
            source_sha256="a" * 64,
            valid_votes=2,
            supporting_votes=3,
        )
    with pytest.raises(ValueError, match="unique"):
        DecisionSupport(
            rule="vote",
            source_artifact="source",
            source_sha256="a" * 64,
            model_ids=("same", "same"),
        )
