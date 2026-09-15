"""Regression coverage for availability and authority-aware partial updates."""

import pytest

from standards_atlas.domain.model import (
    Clause,
    ClauseApplicability,
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
    updated = merge(original, role_semantics_present=False, process_functions=()).clause
    assert updated.semantic_classification.role_semantics_present is False
    assert updated.provenance.availability("enrichments.semantic.role_semantics_present") == "known"
    assert updated.provenance.availability("enrichments.semantic.process_functions") == "known"
    assert (
        original.provenance.availability("enrichments.semantic.role_semantics_present")
        == "not_evaluated"
    )


def test_presence_without_details_roundtrips_canonical_model():
    result = merge(clause(), role_semantics_present=True).clause
    assert Clause.model_validate_json(result.model_dump_json()) == result
    assert result.semantic_classification.role_relations == ()


def test_negative_role_presence_clears_stale_details_but_not_other_dimensions():
    current = clause(
        role_semantics_present=True,
        role_relation_types=("responsible_for",),
        knowledge_kinds=("process",),
    )
    result = merge(current, role_semantics_present=False).clause
    assert result.semantic_classification.role_relation_types == ()
    assert result.semantic_classification.knowledge_kinds == ("process",)


def merge_applicability(current, value, *, availability="known"):
    attribute = GeneratedAttribute(
        path="enrichments.applicability",
        generator="test",
        method=GenerationMethod.IMPORTED,
        availability=availability,
    )
    patch = (
        ClauseEnrichmentPatch(applicability=value)
        if availability == "known"
        else ClauseEnrichmentPatch()
    )
    return merge_generated_enrichments(current, patch, (attribute,))


def test_applicability_is_an_independent_typed_enrichment():
    value = ClauseApplicability(present=True, polarity="included")
    result = merge_applicability(clause(), value).clause
    assert result.applicability == value
    assert result.provenance.availability("enrichments.applicability") == "known"
    assert Clause.model_validate_json(result.model_dump_json()) == result


def test_confirmed_applicability_blocks_generated_replacement():
    path = "enrichments.applicability"
    current = merge_applicability(clause(), ClauseApplicability(present=True)).clause
    current = current.confirm_authoritative(path, authority="atlasdata")
    result = merge_applicability(current, ClauseApplicability(present=False))
    assert result.clause == current
    assert result.changes[0].status == "protected"
    assert result.clause.provenance.protection(path) == "confirmed"


def test_unknown_applicability_preserves_known_value_and_records_unknown_on_empty_state():
    value = ClauseApplicability(present=True)
    current = merge_applicability(clause(), value).clause
    result = merge_applicability(current, None, availability="unknown")
    assert result.clause == current
    empty = merge_applicability(clause(), None, availability="unknown").clause
    assert empty.applicability == ClauseApplicability()
    assert empty.provenance.availability("enrichments.applicability") == "unknown"


def test_replay_is_idempotent():
    first = merge(clause(), primary_function="description", statement_functions=("description",))
    second = merge(
        first.clause,
        primary_function="description",
        statement_functions=("description",),
    )
    assert second.clause == first.clause
    assert {item.status for item in second.changes} == {"unchanged"}


def test_patch_requires_provenance_for_canonical_applicability():
    with pytest.raises(ValueError, match="provenance"):
        merge_generated_enrichments(
            clause(),
            ClauseEnrichmentPatch(applicability=ClauseApplicability(present=True)),
            (),
        )


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
