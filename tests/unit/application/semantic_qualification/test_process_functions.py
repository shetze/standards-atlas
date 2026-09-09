"""Process observations must survive qualification without manufacturing negatives."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import yaml

from standards_atlas.application.semantic_qualification.annotations import (
    AnnotationGenerator,
    ClauseEvaluationAnnotation,
    ClauseReference,
    StatementFunctionSelection,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
    ModelConsensusService,
    ModelVote,
    _resolve_clause,
)
from standards_atlas.application.semantic_qualification.process_functions import (
    PROCESS_CLAUSE_FIELDS,
    PROCESS_VOTE_FIELDS,
    process_vote,
    resolve_process_votes,
    with_process_observation_fields,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    CascadeResolutionConfig,
    ConsensusPromptSelection,
    capture_resolved_dimensions,
    cascade_escalation_reasons,
    cascade_stage_escalation_reasons,
)

NOW = datetime(2026, 9, 9, tzinfo=UTC)
FIELDS = ("process_functions", "primary_process_function")


def annotation(members=(), primary=None, *, supplied=FIELDS, model="m"):
    return ClauseEvaluationAnnotation(
        task="semantic-profile-classification",
        lifecycle_status="proposed",
        clause=ClauseReference(
            knowledge_domain="test",
            document_key="TEST",
            clause_id="c1",
            content_hash="sha256:" + "a" * 64,
        ),
        proposal=StatementFunctionSelection(
            statement_functions=("requirement",),
            primary_function="requirement",
            process_functions=members,
            primary_process_function=primary,
            confidence=0.9,
            rationale="Untrusted prose: process_functions=[output].",
        ),
        generator=AnnotationGenerator(
            provider="fake",
            model=model,
            prompt_id="p",
            generated_at=NOW,
            input_hash="input",
            raw_response_hash="response",
            provided_fields=supplied,
        ),
    )


def vote(model="m", members=("activity",), primary="activity", *, evaluated=True):
    return ModelVote(
        model_id=model,
        repetitions=1,
        stability=1.0,
        primary_function="requirement",
        primary_knowledge_kind="process",
        process_functions=members,
        primary_process_function=primary,
        process_primary_evaluated=evaluated,
    )


def resolve(votes, *, minimum=2):
    return resolve_process_votes(
        tuple(votes),
        minimum_models=minimum,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
    )


def clause(votes, *, minimum=2, override=None):
    fields = _resolve_clause(
        votes=tuple(votes),
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=minimum,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
        resolution_override=override,
    )
    return ClauseConsensus(clause_id="c1", document_key="TEST", votes=tuple(votes), **fields)


def test_missing_fields_do_not_vote_and_empty_fields_do():
    omitted = vote("missing", None, None, evaluated=False)
    positive = resolve([vote("a"), vote("b"), omitted])
    assert positive["process_participating_models"] == 2
    assert positive["process_primary_support"] == {"activity": 1.0}
    assert positive["process_set_category"] == ConsensusCategory.UNANIMOUS
    empty = resolve([vote("a", (), None), vote("b", (), None), omitted])
    assert empty["proposed_process_functions"] == ()
    assert empty["process_set_decided"] and empty["process_primary_decided"]
    assert empty["process_primary_support"] == {"none": 1.0}
    assert empty["process_exact_set_agreement"] == 1.0
    absent = resolve([omitted])
    assert not absent["process_set_evaluated"] and not absent["process_primary_evaluated"]
    assert not absent["process_set_decided"]
    assert absent["process_primary_category"] == ConsensusCategory.INSUFFICIENT


def test_primary_tie_does_not_discard_an_agreed_set():
    members = ("activity", "output")
    result = resolve([vote("a", members, "activity"), vote("b", members, "output")])
    assert result["primary_process_function"] is None
    assert not result["process_primary_decided"]
    assert result["process_primary_category"] == ConsensusCategory.DISPUTED
    assert result["process_set_decided"]
    assert result["proposed_process_functions"] == members
    assert result["process_set_confidence"] == 1.0


def test_a_set_tie_is_not_an_explicit_empty_decision():
    result = resolve([vote("a"), vote("b", (), None)])
    assert result["proposed_process_functions"] == ()
    assert result["process_set_evaluated"]
    assert not result["process_set_decided"]
    assert result["process_set_category"] == ConsensusCategory.DISPUTED


def test_per_label_majorities_are_separate_from_exact_set_agreement():
    result = resolve(
        [
            vote("a", ("activity", "input")),
            vote("b", ("activity", "output")),
            vote("c", ("activity", "input", "output")),
        ],
        minimum=3,
    )
    assert result["proposed_process_functions"] == ("activity", "input", "output")
    assert result["process_set_confidence"] == pytest.approx(2 / 3)
    assert result["process_exact_set_agreement"] == pytest.approx(1 / 3)
    assert result["process_primary_confidence"] == 1.0


def test_set_only_observation_does_not_supply_a_null_primary():
    result = resolve(
        [
            vote("a", ("activity",), None, evaluated=False),
            vote("b", ("activity",), None, evaluated=False),
        ]
    )
    assert result["process_set_decided"]
    assert not result["process_primary_evaluated"]
    assert result["process_primary_participating_models"] == 0


def test_repetitions_are_one_coherent_vote_not_three_independent_models():
    fields = process_vote(
        [
            annotation(("activity",), "activity"),
            annotation(("activity",), "activity"),
            annotation(("output",), "output"),
        ]
    )
    assert fields["process_repetitions"] == 3
    assert fields["process_stability"] == pytest.approx(2 / 3)
    result = resolve([ModelVote(model_id="m", repetitions=3, stability=1, **fields)])
    assert result["process_participating_models"] == 1
    assert result["process_set_category"] == ConsensusCategory.INSUFFICIENT
    tied = process_vote([annotation(("activity",), "activity"), annotation(("output",), "output")])
    assert "process_functions" not in tied
    assert tied["process_stability"] == 0.5


def test_set_order_does_not_destabilize_repetitions():
    fields = process_vote(
        [
            annotation(("output", "activity"), "activity"),
            annotation(("activity", "output"), "activity"),
        ]
    )
    assert fields["process_stability"] == 1.0
    assert fields["process_functions"] == ("activity", "output")


def test_normalizer_defaults_are_not_observations():
    assert process_vote([annotation((), None, supplied=())]) == {}
    assert process_vote([annotation(("activity",), "activity", supplied=None)]) == {}
    partial = process_vote([annotation(("activity",), None, supplied=("process_functions",))])
    assert partial["process_functions"] == ("activity",)
    assert not partial["process_primary_evaluated"]


@pytest.mark.parametrize(
    "change", ["none", "input", "model", "prompt", "response_hash", "text_only", "invalid"]
)
def test_legacy_replay_uses_only_matching_structured_response(tmp_path, change):
    original = annotation((), None, supplied=None)
    response = {
        "provider": "fake",
        "model": "m",
        "prompt_version": "p",
        "input_hash": "input",
        "raw_response_hash": "response",
        "value": {"process_functions": [], "primary_process_function": None},
    }
    if change == "input":
        response["input_hash"] = "different"
    elif change == "model":
        response["model"] = "different"
    elif change == "prompt":
        response["prompt_version"] = "other-prompt"
    elif change == "response_hash":
        response["raw_response_hash"] = "different"
    elif change == "text_only":
        response["value"] = {"rationale": "process_functions=[], primary_process_function=null"}
    elif change == "invalid":
        response["value"]["process_functions"] = ["invented"]
    path = tmp_path / "response.json"
    path.write_text(json.dumps(response))
    before = path.read_bytes()
    recovered = with_process_observation_fields(original, tmp_path)
    assert path.read_bytes() == before
    assert recovered.generator.provided_fields == (FIELDS if change == "none" else ())
    assert original.generator.provided_fields is None


def test_legacy_missing_or_default_filled_interviews_are_not_reconstructed(tmp_path):
    original = annotation(supplied=None)
    assert with_process_observation_fields(original, tmp_path).generator.provided_fields == ()
    (tmp_path / "interview.json").write_text('{"aggregated_selection":{"process_functions":[]}}')
    (tmp_path / "response.json").write_text(
        json.dumps(
            {
                "provider": "fake",
                "model": "m",
                "prompt_version": "p",
                "input_hash": "input",
                "raw_response_hash": "response",
                "value": {"process_functions": [], "primary_process_function": None},
            }
        )
    )
    assert with_process_observation_fields(original, tmp_path).generator.provided_fields == ()


def test_duplicate_models_and_inconsistent_vote_values_are_rejected():
    with pytest.raises(ValueError, match="unique model ids"):
        resolve([vote(), vote()])
    with pytest.raises(ValueError, match="explicitly observed"):
        vote(members=("activity",), primary="output")
    with pytest.raises(ValueError, match="observed set"):
        vote(members=None, primary=None)


def test_missing_process_prompt_never_falls_back_to_another_prompt(tmp_path):
    observations = []
    for model in ("a", "b", "c"):
        directory = tmp_path / model
        case = directory / "c1"
        case.mkdir(parents=True)
        (case / "evaluation.yaml").write_text(
            yaml.safe_dump(
                {
                    "annotation_candidate": annotation(
                        ("activity",), "activity", model=model
                    ).model_dump(mode="json", exclude_none=True)
                }
            )
        )
        observations.append(
            SimpleNamespace(
                model_id=model,
                prompt_id="p",
                reasoning_mode_id="off",
                run_directory=directory,
            )
        )
    kwargs = dict(
        matrix_id="test",
        corpus_id="test",
        prompt_id="p",
        reasoning_mode_id="off",
        observations=tuple(observations),
        output_directory=tmp_path / "consensus",
        min_models=3,
    )
    missing, *_ = ModelConsensusService().evaluate(
        **kwargs, prompt_selection={"process_function": "q"}
    )
    assert not missing.clauses[0].process_set_evaluated
    report, json_path, proposal_path, review_path = ModelConsensusService().evaluate(**kwargs)
    c = report.clauses[0]
    assert c.process_primary_decided and c.primary_process_function == "activity"
    assert c.process_participating_models == 3
    assert ConsensusReport.model_validate_json(json_path.read_text()) == report
    proposal = yaml.safe_load(proposal_path.read_text())
    assert proposal["schema_version"] == "4.0"
    assert proposal["clauses"][0]["process_functions"] == ["activity"]
    assert "Process-function coverage" in review_path.read_text()
    assert report.process_function_metrics["set_evaluated"] == 1


def test_legacy_consensus_serialization_preserves_fingerprint_payload():
    report = ConsensusReport(
        matrix_id="m",
        corpus_id="c",
        prompt_id="p",
        reasoning_mode_id="off",
        generated_at=NOW,
        model_count=2,
        clause_count=1,
        categories={},
        review_count=0,
        clauses=(
            clause(
                [vote("a", None, None, evaluated=False), vote("b", None, None, evaluated=False)]
            ),
        ),
    )
    legacy = report.model_dump(mode="json")
    legacy["schema_version"] = "4.0"
    legacy.pop("process_function_metrics")
    for item in legacy["clauses"]:
        for field in PROCESS_CLAUSE_FIELDS:
            item.pop(field)
        for model_vote in item["votes"]:
            for field in PROCESS_VOTE_FIELDS:
                model_vote.pop(field)
    loaded = ConsensusReport.model_validate(legacy)
    assert not loaded.clauses[0].process_set_evaluated
    assert loaded.model_dump(mode="json") == legacy
    positive = report.model_dump(mode="python")
    positive["schema_version"] = "4.0"
    positive["clauses"] = (clause([vote("a"), vote("b")]),)
    with pytest.raises(ValueError, match="schema 5.0"):
        ConsensusReport.model_validate(positive)


def process_resolution(**updates):
    return CascadeResolutionConfig(
        minimum_successful_models=2,
        escalate_on_knowledge_kind_disagreement=False,
        escalate_on_applicability_disagreement=False,
        escalate_on_role_relation_disagreement=False,
        **updates,
    )


def test_process_escalation_is_opt_in_and_tracks_only_measured_models():
    c = clause([vote("a"), vote("b", None, None, evaluated=False)])
    assert not any(
        "process" in reason for reason in cascade_escalation_reasons(c, process_resolution())
    )
    reasons = cascade_escalation_reasons(
        c, process_resolution(minimum_process_function_confidence=0.6)
    )
    assert "insufficient_process_function_models" in reasons
    missing = clause(
        [vote("a", None, None, evaluated=False), vote("b", None, None, evaluated=False)]
    )
    reasons = cascade_escalation_reasons(
        missing, process_resolution(minimum_process_set_confidence=0.6)
    )
    assert "process_set_unavailable" in reasons
    assert "insufficient_process_set_models" in reasons


def test_primary_and_set_snapshots_preserve_earlier_resolutions():
    first = clause([vote("a"), vote("b")])
    snapshots = capture_resolved_dimensions(
        cumulative_clause=first,
        stage_clause=first,
        source="efficient",
        previous_reasons=(),
        remaining_reasons=(),
        initial_stage=True,
        resolution=process_resolution(),
    )
    assert {"process_function", "process_set"}.issubset(snapshots)
    later = [vote("c", ("output",), "output"), vote("d", ("output",), "output")]
    final = clause(later, override=snapshots)
    assert final.primary_process_function == "activity"
    assert final.proposed_process_functions == ("activity",)
    assert final.process_function_support == {"activity": 1.0}
    assert final.resolution_sources["process_set"] == "efficient"


def test_stage_resolver_uses_its_own_source_and_does_not_reopen_resolved_sets():
    cumulative = clause([vote("a"), vote("b", ("output",), "output")])
    resolver = clause([vote("resolver", ("output",), "output")], minimum=1)
    config = process_resolution(
        minimum_process_function_confidence=0.6,
        process_function_resolution_mode="stage_resolver",
    )
    remaining = cascade_stage_escalation_reasons(
        cumulative_clause=cumulative,
        stage_clause=resolver,
        previous_reasons=("process_function_disagreement",),
        resolution=config,
    )
    assert not any("process" in reason for reason in remaining)
    captured = capture_resolved_dimensions(
        cumulative_clause=cumulative,
        stage_clause=resolver,
        process_stage_clause=resolver,
        previous_reasons=("process_function_disagreement",),
        remaining_reasons=remaining,
        source="final",
        resolution=config,
    )
    assert captured["process_function"]["source"] == "final/stage-resolver"
    assert "process_set" not in captured


def test_no_snapshot_for_missing_process_data_and_conflicts_are_visible():
    missing = clause(
        [vote("a", None, None, evaluated=False), vote("b", None, None, evaluated=False)]
    )
    captured = capture_resolved_dimensions(
        cumulative_clause=missing,
        stage_clause=missing,
        previous_reasons=(),
        remaining_reasons=(),
        source="efficient",
        initial_stage=True,
    )
    assert "process_function" not in captured and "process_set" not in captured
    first = clause([vote("a"), vote("b")])
    captured = capture_resolved_dimensions(
        cumulative_clause=first,
        stage_clause=first,
        previous_reasons=(),
        remaining_reasons=(),
        source="efficient",
        initial_stage=True,
    )
    final = clause(
        [vote("c", ("output",), "output"), vote("d", ("output",), "output")],
        override={"process_function": captured["process_function"]},
    )
    assert final.process_decision_conflict
    assert final.requires_review


def test_process_prompt_inherits_statement_prompt_unless_explicit():
    assert ConsensusPromptSelection(statement_function="s").process_function == "s"
    explicit = ConsensusPromptSelection(statement_function="s", process_function="p")
    assert explicit.process_function == "p"


def test_tied_repetitions_are_measured_but_not_a_negative_decision():
    fields = process_vote(
        [annotation(("activity",), "activity"), annotation(("output",), "output")]
    )
    result = resolve([ModelVote(model_id="m", repetitions=2, stability=0.5, **fields)])
    assert result["process_set_evaluated"] and result["process_primary_evaluated"]
    assert result["process_participating_models"] == 0
    assert result["process_primary_participating_models"] == 0
    assert not result["process_set_decided"] and not result["process_primary_decided"]
