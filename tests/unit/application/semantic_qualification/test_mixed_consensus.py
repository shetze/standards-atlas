"""Slice 5: attribute-specific support, source acceptance and shared routing."""

from dataclasses import replace

import pytest
from test_partial_observations import RESOURCES, config, example, observation, prepared

from standards_atlas.application.semantic_qualification.consensus import ModelConsensusService
from standards_atlas.application.semantic_qualification.mixed_evidence import (
    AttributeAcceptance,
    CompletionProfile,
    StagedPartialObservation,
)
from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_ATTRIBUTES,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    CascadeResolutionConfig,
    ConsensusConfig,
    cascade_escalation_reasons,
    cascade_stage_unresolved_clause_ids,
    cascade_unresolved_clause_ids,
)

VALUES = {
    "primary_function": "definition",
    "statement_functions": ["definition"],
    "primary_knowledge_kind": "process",
    "knowledge_kinds": ["process"],
    "primary_process_function": None,
    "process_functions": [],
    "applicability_present": False,
    "role_semantics_present": False,
    "role_relations": [],
}


def votes(item=None, *, fields=PARTIAL_ATTRIBUTES, n=3, changes=None, stage="efficient", start=0):
    item = item or example()
    results = []
    for index in range(start, start + n):
        request = prepared(cfg=config(selected_attributes=fields), item=item)
        values = {key: VALUES[key] for key in request.plan.requested_attributes}
        values.update((changes or {}).get(index, {}))
        obs = observation(request, values).model_copy(update={"model": f"m{index}"})
        results.append(
            StagedPartialObservation(stage=stage, model_id=f"id{index}", observation=obs)
        )
    return tuple(results)


def evaluate(
    *,
    items=None,
    observations=(),
    resolution=None,
    previous=None,
    completion_profile=None,
    stage="efficient",
    stage_model_count=3,
):
    return ModelConsensusService().evaluate_partial(
        matrix_id="test",
        corpus_id="test-partial",
        stage_id=stage,
        examples=items or (example(),),
        observations=observations,
        resolution=resolution or CascadeResolutionConfig(),
        consensus=ConsensusConfig(),
        resources=RESOURCES,
        previous=previous,
        stage_model_count=stage_model_count,
        completion_profile=completion_profile or CompletionProfile(),
    )


def test_every_selected_clause_survives_without_any_model():
    result = evaluate(items=(example("a"), example("b", confirmed=True)))
    assert result.clause_count == 2 and result.completed_count == 0
    assert result.clauses[0].decision("applicability_present").value is None
    fixed = result.clauses[1].decision("primary_function")
    assert fixed.known and fixed.value == "definition" and fixed.source == "deterministic"
    assert fixed.confidence is None and fixed.observed_model_count == 0
    assert fixed.model_values == {} and fixed.supporting_models == ()
    assert result.clauses[1].decision("statement_functions").status == "not_evaluated"


def test_fully_predecided_focused_profile_needs_zero_models_but_not_80_percent_claim():
    result = evaluate(
        items=(example(confirmed=True),),
        completion_profile=CompletionProfile(required_attributes=("primary_function",)),
    )
    assert result.completed_count == 1
    assert result.metrics["benchmark_eligible"] is False
    assert not result.clauses[0].fully_evaluated


def test_normal_full_sparse_observations_resolve_without_synthetic_votes():
    result = evaluate(observations=votes())
    assert result.completed_count == 1
    assert result.clauses[0].fully_evaluated
    for decision in result.clauses[0].decisions:
        assert decision.observed_model_count == 3
    assert result.clauses[0].decision("applicability_present").value is False
    assert result.clauses[0].decision("process_functions").value == []


def test_minimum_models_is_per_attribute_not_per_clause():
    observations = (
        *votes(fields=("primary_function",), n=4),
        *votes(fields=("applicability_present",), n=2, start=4),
    )
    clause = evaluate(observations=observations).clauses[0]
    assert clause.decision("primary_function").known
    app = clause.decision("applicability_present")
    assert app.observed_model_count == 2 and app.value is None
    assert "insufficient_models" in app.reasons
    assert clause.decision("role_semantics_present").observed_model_count == 0


def test_duplicate_retries_and_repetitions_never_add_voters():
    observed = votes(n=1)
    result = evaluate(observations=observed * 9)
    assert result.clauses[0].decision("primary_function").observed_model_count == 1
    assert result.completed_count == 0


def test_same_model_conflicting_same_stage_is_rejected():
    with pytest.raises(ValueError, match="same model"):
        evaluate(
            observations=(*votes(n=1), *votes(n=1, changes={0: {"applicability_present": True}}))
        )


def test_later_same_model_replaces_an_open_answer_not_adds_a_voter():
    observed = (
        *votes(n=1),
        *votes(n=1, stage="second", changes={0: {"applicability_present": True}}),
    )
    app = (
        evaluate(observations=observed, stage="second").clauses[0].decision("applicability_present")
    )
    assert app.observed_model_count == 1 and app.proposed_value is True


def test_source_term_decides_only_primary_without_required_model_minimum():
    item = example(confirmed=True)
    result = evaluate(items=(item,), observations=votes(item, n=3))
    primary = result.clauses[0].decision("primary_function")
    assert primary.source == "deterministic" and primary.confidence is None
    assert result.completed_count == 1


def test_fixed_primary_does_not_accept_unasked_secondary_set():
    item = example(confirmed=True)
    result = evaluate(items=(item,), observations=votes(item, fields=("applicability_present",)))
    assert result.clauses[0].decision("statement_functions").status == "not_evaluated"


def test_explicit_absent_primary_is_not_missing_observation_but_does_not_classify():
    observed = votes(changes={i: {"primary_function": None} for i in range(3)})
    decision = evaluate(observations=observed).clauses[0].decision("primary_function")
    assert decision.observed_model_count == 3
    assert decision.status == "unresolved" and "no_primary_classification" in decision.reasons


def test_presence_disagreement_remains_strict_until_separate_policy_slice():
    observed = votes(n=4, changes={0: {"applicability_present": True}})
    decision = evaluate(observations=observed).clauses[0].decision("applicability_present")
    assert not decision.known and "disagreement" in decision.reasons


def test_role_minority_conflict_is_not_silently_relaxed():
    relation = [{"actor": "supplier", "relation_class": "responsibility", "target": "review"}]
    observed = votes(n=4, changes={0: {"role_semantics_present": True, "role_relations": relation}})
    resolution = CascadeResolutionConfig(
        escalate_on_role_relation_disagreement=False, minimum_role_relation_confidence=0.75
    )
    clause = evaluate(observations=observed, resolution=resolution).clauses[0]
    assert "role_semantics_evidence_conflict" in clause.decision("role_semantics_present").reasons
    assert clause.requires_review


def test_prior_acceptance_remains_stable_with_original_votes_and_stage():
    initial = votes()
    first = evaluate(observations=initial)
    later = votes(
        n=2,
        start=3,
        stage="second",
        changes={
            3: {"primary_function": "description", "statement_functions": ["description"]},
            4: {"primary_function": "description", "statement_functions": ["description"]},
        },
    )
    final = evaluate(observations=(*initial, *later), previous=first, stage="second")
    decision = final.clauses[0].decision("primary_function")
    assert decision.value == "definition" and decision.stage == "efficient"
    assert decision.observed_model_count == 3
    assert "later_model_dissent" in decision.diagnostics


def test_two_model_stage_resolver_does_not_accept_a_half_vote_or_a_single_survivor():
    resolution = CascadeResolutionConfig(
        minimum_successful_models=5, statement_function_resolution_mode="stage_resolver"
    )
    for observed in (
        votes(n=1, stage="final"),
        votes(
            n=2,
            stage="final",
            changes={
                1: {"primary_function": "description", "statement_functions": ["description"]}
            },
        ),
    ):
        clause = evaluate(
            observations=observed, resolution=resolution, stage="final", stage_model_count=2
        ).clauses[0]
        assert not clause.decision("primary_function").known
    clause = evaluate(
        observations=votes(n=2, stage="final"),
        resolution=resolution,
        stage="final",
        stage_model_count=2,
    ).clauses[0]
    assert clause.decision("primary_function").known
    assert clause.decision("primary_knowledge_kind").observed_model_count == 2
    assert not clause.decision("primary_knowledge_kind").known


def test_primary_is_never_inserted_into_a_conflicting_evaluated_set():
    observed = (
        *votes(fields=("primary_function",)),
        *votes(
            fields=("statement_functions",),
            start=3,
            changes={i: {"statement_functions": ["description"]} for i in range(3, 6)},
        ),
    )
    clause = evaluate(observations=observed).clauses[0]
    assert clause.decision("primary_function").value == "definition"
    assert clause.decision("statement_functions").status == "conflict"
    assert clause.decision("statement_functions").value is None
    assert clause.requires_review and clause.consistency_reasons


def test_sets_require_own_evidence_not_union_or_primary_repair():
    observed = votes(
        changes={
            0: {"knowledge_kinds": ["process", "concept"]},
            1: {"knowledge_kinds": ["process", "role"]},
            2: {"knowledge_kinds": ["process", "artifact"]},
        }
    )
    decision = evaluate(observations=observed).clauses[0].decision("knowledge_kinds")
    assert decision.proposed_value == ["process"]
    assert decision.status == "unresolved"  # No model claimed this as a complete set.


def test_source_conflict_is_not_overridden_by_unanimous_models():
    item = example(clause_type="objective", heading="Work products")
    result = evaluate(items=(item,), observations=votes(item))
    # Whether a source pattern is a hint or conflict is defined by Slice 2.
    source = result.clauses[0].decision_plan.decision("primary_function")
    if source.state == "conflict":
        assert result.clauses[0].decision("primary_function").status == "conflict"
    else:
        assert source.state != "fixed"


def test_routing_and_review_share_one_decision_and_all_selected_ids():
    resolution = CascadeResolutionConfig()
    report = evaluate(items=(example("a"), example("b")), observations=votes(example("a")))
    pending, reasons = cascade_unresolved_clause_ids(
        report.clauses, stage_clause_ids=("a", "b", "missing"), resolution=resolution
    )
    assert pending == ("b", "missing")
    assert reasons["a"] == () and not report.clauses[0].requires_review
    assert reasons["b"] == report.clauses[1].review_reasons
    assert reasons["missing"] == ("no_consensus_result",)
    result, _ = cascade_stage_unresolved_clause_ids(
        report.clauses,
        report.clauses,
        stage_clause_ids=("b",),
        previous_reasons={"b": reasons["b"]},
        resolution=resolution,
    )
    assert result == ("b",)
    with pytest.raises(ValueError, match="resolutions differ"):
        cascade_escalation_reasons(
            report.clauses[0], CascadeResolutionConfig(minimum_confidence=0.9)
        )


def test_expected_labels_and_tags_do_not_change_consensus():
    item = example()
    changed = replace(item, expected={"primary_function": "prohibition"}, tags=("other",))
    assert evaluate(items=(item,), observations=votes(item)) == evaluate(
        items=(changed,), observations=votes(changed)
    )


def test_selection_and_completion_profile_cannot_change_mid_cascade():
    first = evaluate()
    with pytest.raises(ValueError, match="selection or policy"):
        evaluate(items=(example("changed"),), previous=first)
    with pytest.raises(ValueError, match="selection or policy"):
        evaluate(
            previous=first,
            completion_profile=CompletionProfile(required_attributes=("primary_function",)),
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"observed_model_count": 1},
        {"confidence": 1.0},
        {"model_values": {"fake": "definition"}, "observed_model_count": 1},
    ],
)
def test_taxonomy_evidence_cannot_claim_model_support(changes):
    payload = dict(
        attribute="primary_function",
        status="accepted",
        value="definition",
        source="deterministic",
        stage="first",
        rule="rule",
    )
    with pytest.raises(ValueError):
        AttributeAcceptance(**{**payload, **changes})
