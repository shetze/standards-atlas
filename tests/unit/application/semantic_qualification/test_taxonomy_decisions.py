"""Diagnostic rule contracts, authority separation and source-only inputs."""

import copy
import json
from importlib.resources import files

import pytest
import yaml
from pydantic import ValidationError

from standards_atlas.application.context.source_structure import project_source_structure
from standards_atlas.application.model.source_structure import SourceStructure
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.structural_evidence import (
    derive_structural_evidence,
    taxonomy_structural_evidence,
)
from standards_atlas.application.semantic_qualification.taxonomy_decisions import (
    DECISION_ATTRIBUTES,
    RESOURCE_DIRECTORY,
    ClauseDecisionPlan,
    TaxonomyRule,
    derive_clause_decision_plan,
    load_taxonomy_rules,
)
from standards_atlas.domain.model import Clause, ClauseId, ClauseType, StandardReference, TextBlock
from standards_atlas.domain.model.knowledge_state import (
    GeneratedAttribute,
    GenerationMethod,
    KnowledgeStateProvenance,
)


def context(**changes):
    return {"document_key": "TEST", "clause_id": "test-1", "reference": "3.1", **changes}


def plan(*, text="A source clause.", **changes):
    return derive_clause_decision_plan(context(**changes), text=text)


def canonical_clause(**changes):
    return Clause(
        id=ClauseId(value="test-1"),
        reference=StandardReference(standard="TEST", clause="3.1"),
        clause_type=changes.pop("clause_type", ClauseType.TERM),
        heading=changes.pop("heading", "process"),
        content=(TextBlock(id="text-1", text="A sequence of activities."),),
        **changes,
    )


def canonical_plan(clause, *, parents=()):
    source = project_source_structure(
        clause,
        document_key="TEST",
        content_hash=normalized_content_hash(clause.plain_text),
        ancestors=parents,
    )
    return plan(
        text=clause.plain_text,
        source_structure=source.model_dump(mode="json"),
        clause_type=clause.clause_type.value,
        heading=clause.heading,
    )


@pytest.mark.parametrize("heading", ["process", "assessor", "analysis technique"])
def test_confirmed_term_fixes_only_primary_definition(heading):
    result = canonical_plan(
        canonical_clause(heading=heading).confirm_authoritative(
            "clause_type",
            authority="reviewed-source",
        )
    )
    assert result.decision("primary_function").state == "fixed"
    assert result.decision("primary_function").value == "definition"
    for attribute in DECISION_ATTRIBUTES[1:]:
        assert result.decision(attribute).state == "open"
    assert result.diagnostic_only is True
    assert "confidence" not in result.model_dump_json()
    assert "valid_votes" not in result.model_dump_json()
    assert "applicability_functions" not in [item.attribute for item in result.decisions]


@pytest.mark.parametrize("origin", ["legacy", "canonical", "deterministic"])
def test_unconfirmed_source_is_never_promoted_to_authority(origin):
    clause = canonical_clause()
    if origin == "deterministic":
        clause = clause.model_copy(
            update={
                "provenance": KnowledgeStateProvenance(
                    generated_attributes=(
                        GeneratedAttribute(
                            path="clause_type",
                            generator="heuristic",
                            method=GenerationMethod.DETERMINISTIC,
                        ),
                    ),
                )
            }
        )
    result = plan(clause_type="term") if origin == "legacy" else canonical_plan(clause)
    assert result.decision("primary_function").state == "hint"
    assert result.decision("primary_function").value is None
    assert result.decision("primary_function").candidates == ("definition",)


def test_heading_is_read_and_legacy_alias_is_only_a_reader_fallback():
    result = plan(heading="Objectives")
    assert result.decision("primary_function").candidates == ("objective",)
    assert result.decision("primary_function").state == "hint"
    alias = plan(title="Objectives")
    assert alias.fingerprint == result.fingerprint
    canonical_empty = plan(heading=None, title="Objectives")
    assert canonical_empty.decision("primary_function").state == "open"
    assert "conflicting_legacy_title_ignored" in canonical_empty.warnings


def test_current_production_prior_is_explicitly_frozen():
    old = derive_structural_evidence({"heading": "Objectives"}, policy="legacy-v1")
    assert old.primary_function is None
    assert plan(heading="Objectives").decision("primary_function").state == "hint"
    with pytest.raises(ValueError, match="pinned"):
        derive_structural_evidence({}, policy="source-structure-v1")


def test_requirements_on_objectives_is_not_pure_objective():
    result = plan(clause_type="requirement", heading="Requirements on objectives")
    assert result.decision("primary_function").candidates == ("requirement",)
    assert result.decision("primary_function").state == "hint"


@pytest.mark.parametrize("inherited", [False, True])
def test_work_products_is_an_explicit_conflict(inherited):
    changes = {"clause_type": "objective", "heading": "Work products"}
    if inherited:
        changes.update(
            heading="Verification report",
            ancestor_headings=[
                {"clause_id": "parent", "reference": "3", "heading": "Work products"},
            ],
        )
    result = plan(**changes)
    assert result.decision("primary_function").state == "conflict"
    assert result.decision("primary_function").value is None
    assert any(
        item.rule_id == "structural-conflict"
        for item in result.decision("primary_function").evidence
    )


def test_exact_local_contradiction_blocks_a_confirmed_term():
    result = canonical_plan(
        canonical_clause(heading="Requirements").confirm_authoritative(
            "clause_type",
            "baseline.heading",
            authority="reviewed-source",
        )
    )
    assert result.decision("primary_function").state == "conflict"
    assert result.decision("primary_function").value is None


def test_general_ancestor_cannot_override_specific_confirmed_term():
    parent = Clause(
        id=ClauseId(value="parent"),
        reference=StandardReference(standard="TEST", clause="3"),
        clause_type=ClauseType.TOC,
        heading="Objectives",
    )
    result = canonical_plan(
        canonical_clause().confirm_authoritative("clause_type"),
        parents=(parent,),
    )
    assert result.decision("primary_function").state == "fixed"
    assert result.decision("primary_function").value == "definition"
    assert any(
        item.specificity == "enclosing" for item in result.decision("primary_function").evidence
    )


@pytest.mark.parametrize("field", ["heading", "title"])
def test_ancestor_heading_aliases_are_supported_at_the_read_boundary(field):
    result = plan(
        ancestor_headings=[
            {"clause_id": "parent", "reference": "3", field: "Objectives"},
        ]
    )
    assert result.decision("primary_function").candidates == ("objective",)
    assert result.decision("primary_function").state == "hint"


def technique_context():
    text = (
        "Aim: Analyse failures.\n\nDescription: A systematic method.\n\n"
        "NOTE: Clause 7 is not applicable."
    )
    split = text.index("Description:")
    return text, {
        "clause_type": "misc",
        "heading": "Analysis technique",
        "parent_id": "parent",
        "ancestor_headings": [
            {
                "clause_id": "parent",
                "reference": "C",
                "heading": "Overview of techniques and measures for software safety",
            }
        ],
        "semantic_sections": [
            {"label": "Aim", "role": "aim", "start_offset": 0, "end_offset": split},
            {
                "label": "Description",
                "role": "description",
                "start_offset": split,
                "end_offset": len(text),
            },
        ],
        "structural_context": {"node_kind": "leaf", "child_clause_ids": []},
    }


def test_catalogue_boundary_segments_yield_only_reviewable_knowledge_hint():
    text, data = technique_context()
    result = plan(text=text, **data)
    knowledge = result.decision("primary_knowledge_kind")
    assert knowledge.state == "hint"
    assert knowledge.candidates == ("technique_or_measure",)
    assert knowledge.evidence[0].rule_id == "technique-entry"
    assert result.decision("primary_function").state == "open"
    for attribute in ("applicability_present", "role_semantics_present", "knowledge_kinds"):
        assert result.decision(attribute).state == "open"
    # The note remains part of the content identity, not silently cut off.
    assert result.source.content_hash == normalized_content_hash(text)


@pytest.mark.parametrize("missing", ["ancestor_headings", "structural_context"])
def test_aim_description_without_catalogue_or_boundary_is_not_a_verified_entry(missing):
    text, data = technique_context()
    del data[missing]
    result = plan(text=text, **data)
    knowledge = result.decision("primary_knowledge_kind")
    assert knowledge.state == "hint"
    assert knowledge.evidence[0].rule_id == "technique-segments"


@pytest.mark.parametrize("change", ["overlap", "outside", "bad-label", "wrong-role", "node"])
def test_invalid_segments_and_non_leaf_boundaries_do_not_match_catalogue_rule(change):
    text, data = technique_context()
    sections = data["semantic_sections"]
    if change == "overlap":
        sections[1]["start_offset"] = 0
    elif change == "outside":
        sections[1]["end_offset"] += 1
    elif change == "bad-label":
        sections[0]["label"] = "Unrelated"
    elif change == "wrong-role":
        sections[0]["role"] = "description"
    else:
        data["structural_context"]["child_clause_ids"] = ["child"]
        data["structural_context"]["node_kind"] = "node"
    result = plan(text=text, **data)
    assert not any(
        item.rule_id == "technique-entry"
        for item in result.decision("primary_knowledge_kind").evidence
    )


@pytest.mark.parametrize("clause_type", ["term", "objective", "requirement", "misc", "toc"])
@pytest.mark.parametrize(
    "text",
    [
        "This method is suitable for testing.",
        "NOTE: The requirements of clause 7 do not apply.",
        "The test shall be performed.",
    ],
)
def test_structure_alone_never_decides_applicability(clause_type, text):
    result = plan(clause_type=clause_type, text=text)
    assert result.decision("applicability_present").state == "open"


def test_prohibition_granularity_is_not_fixed_from_requirement_type():
    result = plan(clause_type="requirement", text="The system shall not restart automatically.")
    assert result.decision("primary_function").candidates == ("prohibition",)
    assert result.decision("primary_function").state == "hint"


@pytest.mark.parametrize(
    "field",
    [
        "semantic",
        "subject_context",
        "context_routing",
        "expected",
        "structural_roles",
        "attribute_sources",
        "eligibility",
    ],
)
def test_semantic_answers_and_gold_do_not_change_decisions_or_fingerprints(field):
    data = context(clause_type="term", heading="process")
    reference = derive_clause_decision_plan(data, text="A sequence of activities.")
    data[field] = {"primary_function": "LEAK", "applicability_present": True}
    contaminated = derive_clause_decision_plan(data, text="A sequence of activities.")
    assert contaminated == reference
    assert contaminated.fingerprint == reference.fingerprint
    assert "LEAK" not in contaminated.model_dump_json()


def test_generated_baseline_interpretation_cannot_become_source_evidence():
    clause = canonical_clause().model_copy(
        update={
            "provenance": KnowledgeStateProvenance(
                generated_attributes=(
                    GeneratedAttribute(
                        path="clause_type",
                        generator="llm-classifier",
                        method=GenerationMethod.LLM,
                    ),
                ),
            )
        }
    )
    result = canonical_plan(clause)
    assert result.decision("primary_function").state == "open"
    type_fact = next(fact for fact in result.source.facts if fact.field == "clause_type")
    assert type_fact.origin == "excluded"
    assert type_fact.value is None


def test_unknown_source_is_not_a_negative_value():
    clause = canonical_clause().model_copy(
        update={
            "provenance": KnowledgeStateProvenance(
                generated_attributes=(
                    GeneratedAttribute(
                        path="clause_type",
                        generator="detector",
                        method=GenerationMethod.DETERMINISTIC,
                        availability="unknown",
                    ),
                ),
            )
        }
    )
    result = canonical_plan(clause)
    assert result.decision("primary_function").state == "open"
    assert any(fact.origin == "unavailable" for fact in result.source.facts)


def test_plan_roundtrip_and_fact_order_are_reproducible():
    original = canonical_plan(canonical_clause().confirm_authoritative("clause_type"))
    assert ClauseDecisionPlan.model_validate_json(original.model_dump_json()) == original
    source = original.source.model_dump(mode="json")
    source["facts"].reverse()
    reordered = plan(
        text="A sequence of activities.",
        source_structure=source,
        clause_type="term",
        heading="process",
    )
    assert reordered == original
    assert reordered.fingerprint == original.fingerprint
    projection = taxonomy_structural_evidence(original)
    assert projection["plan_sha256"] == original.fingerprint
    assert projection["attributes"]["primary_function"]["value"] == "definition"
    assert "confidence" not in json.dumps(projection)


@pytest.mark.parametrize("tamper", ["clause_id", "content_hash", "reference", "document_key"])
def test_stale_source_identity_is_rejected(tamper):
    source = canonical_plan(canonical_clause()).source.model_dump(mode="json")
    source[tamper] = "sha256:" + "0" * 64 if tamper == "content_hash" else "other"
    with pytest.raises(ValueError):
        plan(text="A sequence of activities.", source_structure=source)


def test_content_hash_must_match_actual_text():
    with pytest.raises(ValueError, match="content hash"):
        derive_clause_decision_plan(context(), text="real text", content_hash="sha256:" + "0" * 64)


def test_source_and_flat_cbox_must_not_disagree():
    source = canonical_plan(canonical_clause()).source.model_dump(mode="json")
    with pytest.raises(ValueError, match="conflicts with canonical context"):
        plan(text="A sequence of activities.", source_structure=source, clause_type="objective")


def test_rule_evidence_and_source_fingerprint_are_validated():
    raw = canonical_plan(canonical_clause()).model_dump(mode="json")
    bad = copy.deepcopy(raw)
    bad["source_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="fingerprint mismatch"):
        ClauseDecisionPlan.model_validate(bad)
    bad = copy.deepcopy(raw)
    bad["decisions"][0]["evidence"][0]["source_fingerprints"] = ["0" * 64]
    with pytest.raises(ValidationError, match="absent source facts"):
        ClauseDecisionPlan.model_validate(bad)


def test_cannot_promote_a_pending_rule():
    payload = load_taxonomy_rules().rules[1].model_dump()
    payload["maximum_state"] = "fixed"
    with pytest.raises(ValueError, match="unreviewed"):
        TaxonomyRule.model_validate(payload)


def test_unrelated_canonical_fields_cannot_enter_source_contract():
    raw = canonical_plan(canonical_clause()).source.model_dump(mode="json")
    raw["facts"][0]["source_path"] = "enrichments.semantic.primary_function"
    with pytest.raises(ValueError, match="allowlisted baseline"):
        SourceStructure.model_validate(raw)


def test_pending_packaged_review_examples_are_not_published_gold():
    resource = files("standards_atlas.resources").joinpath(RESOURCE_DIRECTORY, "review.yaml")
    review = yaml.safe_load(resource.read_text(encoding="utf-8"))
    assert review["review_status"] == "pending"
    for case in review["cases"]:
        result = plan(text=case["text"], **case["context"])
        assert case["review_status"] == "pending"
        primary = result.decision("primary_function")
        if "expected_primary_candidates" in case:
            assert list(primary.candidates) == case["expected_primary_candidates"], case["id"]
        if "expected_primary_state" in case:
            assert primary.state == case["expected_primary_state"], case["id"]
        if "expected_knowledge_candidates" in case:
            knowledge = result.decision("primary_knowledge_kind")
            assert list(knowledge.candidates) == case["expected_knowledge_candidates"], case["id"]
            assert knowledge.state == case["expected_knowledge_state"], case["id"]
        for attribute in case["must_remain_open"]:
            assert result.decision(attribute).state == "open", (case["id"], attribute)
