"""Slice 6: opt-in ratios and protected minority evidence, not release by vote."""

from pathlib import Path

import pytest
import test_mixed_consensus as fixtures
from pydantic import ValidationError

from standards_atlas.application.semantic_qualification.acceptance_profiles import (
    FocusedResolutionPolicy,
    PartialAcceptanceProfile,
    assess_role_minority,
    profile_from_plan,
    with_acceptance_profile,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    CascadeResolutionConfig,
    cascade_escalation_reasons,
)


def candidate(**kwargs):
    return PartialAcceptanceProfile(id="test-v1", **kwargs)


def evaluate(observations, *, profile=None, resolution=None, **kwargs):
    return fixtures.evaluate(
        observations=observations,
        resolution=with_acceptance_profile(resolution or CascadeResolutionConfig(), profile),
        **kwargs,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"statement_two_thirds": "true"},
        {"statement_two_thirds": 1},
        {"role_evidence_mode": "ignore_all"},
        {"unknown": True},
        {"focused_resolution": {"max_requests": -1}},
        {"focused_resolution": {"models_per_case": 3}},
        {"focused_resolution": {"max_cases": True}},
        {"qualification_status": "qualified"},
        {"version": "0.9"},
    ],
)
def test_profiles_reject_implicit_coercions_and_unreviewed_release(payload):
    with pytest.raises(ValidationError):
        candidate(**payload)


@pytest.mark.parametrize(
    "name",
    [
        "statement-two-thirds-v1",
        "role-evidence-v1",
        "applicability-positive-v1",
        "efficient-evidence-v1",
        "efficient-focused-v1",
    ],
)
def test_shipped_profiles_are_versioned_and_experimental(name):
    profile = PartialAcceptanceProfile.load(Path(f"cfg/evaluation/partial-cascade/{name}.yaml"))
    assert profile.id == name and profile.qualification_status == "experimental"


def test_legacy_resolution_is_byte_shape_identical():
    original = CascadeResolutionConfig()
    assert with_acceptance_profile(original, None) is original
    assert "partial_acceptance" not in original.model_dump()


def test_exact_two_thirds_is_not_decimal_point67_or_rounding():
    obs = fixtures.votes(
        n=3,
        changes={
            2: {
                "primary_function": "description",
                "statement_functions": ["description"],
            }
        },
    )
    old = evaluate(obs).clauses[0].decision("primary_function")
    new = (
        evaluate(obs, profile=candidate(statement_two_thirds=True))
        .clauses[0]
        .decision("primary_function")
    )
    assert old.status == "unresolved" and new.known
    assert new.confidence == 2 / 3
    assert "vote_share:2/3" in new.diagnostics and "required_share:2/3" in new.diagnostics


@pytest.mark.parametrize(
    "n,other,accepted", [(4, 1, True), (4, 2, False), (3, 1, True), (2, 0, False), (3, 2, True)]
)
def test_statement_ratio_and_minimum_are_separate(n, other, accepted):
    changes = {
        i: {"primary_function": "description", "statement_functions": ["description"]}
        for i in range(other)
    }
    value = evaluate(
        fixtures.votes(n=n, changes=changes), profile=candidate(statement_two_thirds=True)
    )
    assert value.clauses[0].decision("primary_function").known is accepted


def test_two_thirds_cannot_bypass_a_higher_stage_floor_or_final_resolver():
    obs = fixtures.votes(
        n=3,
        changes={
            2: {
                "primary_function": "description",
                "statement_functions": ["description"],
            }
        },
    )
    for resolution in (
        CascadeResolutionConfig(minimum_confidence=0.9),
        CascadeResolutionConfig(statement_function_resolution_mode="stage_resolver"),
    ):
        item = evaluate(obs, profile=candidate(statement_two_thirds=True), resolution=resolution)
        assert not item.clauses[0].decision("primary_function").known


@pytest.mark.parametrize(
    "positives,n,accepted",
    [(3, 4, True), (2, 4, False), (2, 3, False), (0, 4, True), (1, 4, False), (1, 9, False)],
)
def test_positive_gate_opens_detail_but_negative_dissent_stays_unknown(positives, n, accepted):
    observations = fixtures.votes(
        n=n, changes={i: {"applicability_present": True} for i in range(positives)}
    )
    report = evaluate(
        observations, profile=candidate(applicability_gate_mode="positive_three_quarters")
    )
    value = report.clauses[0].decision("applicability_present")
    assert value.known is accepted
    if not accepted:
        assert value.value is None


def test_absent_model_evidence_never_becomes_negative():
    report = evaluate((), profile=candidate(applicability_gate_mode="positive_three_quarters"))
    assert report.clauses[0].decision("applicability_present").status == "not_evaluated"
    assert report.clauses[0].decision("applicability_present").value is None


RELATION = {"actor": "supplier", "relation_class": "responsibility", "target": "review"}


def test_isolated_unanchored_role_dissent_is_visible_but_not_an_automatic_veto():
    obs = fixtures.votes(
        n=4, changes={0: {"role_semantics_present": True, "role_relations": [RELATION]}}
    )
    report = evaluate(obs, profile=candidate(role_evidence_mode="anchored_minority"))
    value = report.clauses[0].decision("role_semantics_present")
    assert value.known and value.value is False
    assert any('"suggestion_count": 1' in d for d in value.diagnostics)
    assert value.observed_model_count == 4


@pytest.mark.parametrize(
    "text,actor,anchored",
    [
        ("The supplier shall review.", "supplier", True),
        ("The SUPPLIER shall review.", "supplier", True),
        ("The safety\nmanager decides.", "safety manager", True),
        ("A sub-supplier is appointed.", "supplier", True),
        ("The supplier reviews.", "supplier manager", False),
        ("An assupplier reviews.", "supplier", False),
        ("", "supplier", False),
    ],
)
def test_actor_anchoring_is_conservative_literal_and_word_bounded(text, actor, anchored):
    evidence = assess_role_minority({"m": [{**RELATION, "actor": actor}]}, text=text)
    assert evidence["protective_veto"] is anchored
    assert evidence["semantic_truth_verified"] is False


def test_repeated_attempts_do_not_corroborate_but_distinct_models_do():
    assert not assess_role_minority({"m": [RELATION, RELATION]}, text="None")["protective_veto"]
    assert assess_role_minority({"m": [RELATION], "n": [RELATION]}, text="None")["protective_veto"]


def test_literal_actor_minorities_remain_conflicts_under_large_negative_majority():
    item = fixtures.example()
    item.input["content"]["text"] = "The supplier shall review the result."
    from standards_atlas.application.semantic_qualification.annotations import (
        normalized_content_hash,
    )

    item.input["content"]["hash"] = normalized_content_hash(item.input["content"]["text"])
    obs = fixtures.votes(
        item, n=9, changes={0: {"role_semantics_present": True, "role_relations": [RELATION]}}
    )
    result = evaluate(obs, items=(item,), profile=candidate(role_evidence_mode="anchored_minority"))
    value = result.clauses[0].decision("role_semantics_present")
    assert value.status == "conflict" and value.value is None
    assert value.reasons == ("grounded_minority_role_evidence",)


def test_distinct_corroborated_unanchored_relations_remain_conflict():
    obs = fixtures.votes(
        n=10,
        changes={i: {"role_semantics_present": True, "role_relations": [RELATION]} for i in (0, 1)},
    )
    result = evaluate(obs, profile=candidate(role_evidence_mode="anchored_minority"))
    assert result.clauses[0].decision("role_semantics_present").status == "conflict"


def test_source_decision_is_not_replaced_by_profile_votes():
    item = fixtures.example(confirmed=True)
    result = evaluate(
        fixtures.votes(item), items=(item,), profile=candidate(statement_two_thirds=True)
    )
    value = result.clauses[0].decision("primary_function")
    assert value.source == "deterministic" and value.observed_model_count == 0


def test_routing_review_and_profile_identity_agree():
    profile = candidate(role_evidence_mode="anchored_minority")
    resolution = with_acceptance_profile(CascadeResolutionConfig(), profile)
    result = evaluate(fixtures.votes(), profile=profile)
    clause = result.clauses[0]
    assert clause.completed and not clause.requires_review
    assert cascade_escalation_reasons(clause, resolution) == ()
    with pytest.raises(ValueError, match="resolutions differ"):
        cascade_escalation_reasons(clause, CascadeResolutionConfig())
    with pytest.raises(ValueError, match="profile changed"):
        evaluate(fixtures.votes(), previous=result)


def test_budget_zero_is_supported_without_disabling_validation():
    assert FocusedResolutionPolicy(max_requests=0).max_requests == 0


@pytest.mark.parametrize("payload", [{}, False, [], "", {"id": "x", "version": "wrong"}])
def test_malformed_stored_profiles_never_silently_become_baseline(payload):
    with pytest.raises(ValidationError):
        profile_from_plan({"acceptance_profile": payload})


def test_missing_profile_and_idempotent_runtime_binding():
    assert profile_from_plan({}) is None
    assert profile_from_plan({"acceptance_profile": None}) is None
    profile = candidate(statement_two_thirds=True)
    resolution = with_acceptance_profile(CascadeResolutionConfig(), profile)
    assert with_acceptance_profile(resolution, profile) == resolution
    with pytest.raises(ValueError, match="profile changed"):
        with_acceptance_profile(resolution, candidate(role_evidence_mode="anchored_minority"))
