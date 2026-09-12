from __future__ import annotations

import pytest

from standards_atlas.application.semantic_qualification.cascade_metrics import (
    resolution_counts,
    stage_accounting,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    CascadeResolutionConfig,
    capture_resolved_dimensions,
    cascade_stage_escalation_reasons,
    cascade_stage_unresolved_clause_ids,
    cascade_unresolved_clause_ids,
)
from standards_atlas.cli.commands.evaluation_commands.qualification_matrix import (
    _cascade_reason_dimensions,
)
from standards_atlas.domain.model import StatementFunction


def clause(clause_id: str = "one", confidence: float = 1.0) -> ClauseConsensus:
    category = ConsensusCategory.UNANIMOUS if confidence == 1 else ConsensusCategory.DISPUTED
    return ClauseConsensus(
        clause_id=clause_id,
        document_key="DOC",
        category=category,
        primary_function=StatementFunction.DESCRIPTION,
        confidence=confidence,
        statement_function_confidence=confidence,
        statement_function_category=category,
        participating_models=3,
    )


def test_initial_missing_record_is_not_a_success_and_selection_order_is_preserved() -> None:
    unresolved, reasons = cascade_unresolved_clause_ids(
        [clause("outside"), clause("present")],
        stage_clause_ids=("missing", "present"),
        resolution=CascadeResolutionConfig(),
    )
    assert unresolved == ("missing",)
    assert reasons == {"missing": ("no_consensus_result",), "present": ()}
    metrics = stage_accounting(clause_ids=("missing", "present"), reasons=reasons, selected_count=2)
    assert metrics["completed_clause_count"] == 1
    assert metrics["completed_fraction_of_selection"] == 0.5
    assert metrics["accounted_clause_count"] == 2
    assert metrics["missing_consensus_clause_count"] == 1


@pytest.mark.parametrize(
    "cumulative_exists,local_exists", [(True, False), (False, True), (False, False)]
)
def test_missing_later_records_remain_open_and_do_not_lose_prior_reasons(
    cumulative_exists: bool,
    local_exists: bool,
) -> None:
    prior = ("statement_function_resolver_confidence", "knowledge_kind_confidence")
    unresolved, reasons = cascade_stage_unresolved_clause_ids(
        [clause()] if cumulative_exists else [],
        [clause()] if local_exists else [],
        stage_clause_ids=("one",),
        previous_reasons={"one": prior},
        resolution=CascadeResolutionConfig(),
    )
    assert unresolved == ("one",)
    assert set(prior) <= set(reasons["one"])
    assert ("missing_stage_consensus_result" in reasons["one"]) == (not local_exists)
    assert ("missing_cumulative_consensus_result" in reasons["one"]) == (not cumulative_exists)
    assert (
        capture_resolved_dimensions(
            cumulative_clause=clause(),
            stage_clause=clause(),
            previous_reasons=prior,
            remaining_reasons=reasons["one"],
            source="later",
        )
        == {}
    )


@pytest.mark.parametrize(
    "prior",
    [
        "statement_function_confidence",
        "consensus_category",
        "statement_function_resolver_confidence",
    ],
)
@pytest.mark.parametrize("confidence,expected", [(0.5, True), (0.75, False), (1.0, False)])
def test_every_statement_reason_is_rechecked_against_resolver_threshold(
    prior: str,
    confidence: float,
    expected: bool,
) -> None:
    resolution = CascadeResolutionConfig(statement_function_resolution_mode="stage_resolver")
    remaining = cascade_stage_escalation_reasons(
        cumulative_clause=clause(confidence=0.5),
        stage_clause=clause(confidence=confidence),
        previous_reasons=(prior,),
        resolution=resolution,
    )
    assert bool(remaining) == expected
    capture = capture_resolved_dimensions(
        cumulative_clause=clause(confidence=0.5),
        stage_clause=clause(confidence=confidence),
        previous_reasons=(prior,),
        remaining_reasons=remaining,
        source="final",
        resolution=resolution,
    )
    assert ("statement_function" in capture) == (not expected)


def test_resolver_reason_survives_failure_and_recovers_on_resume() -> None:
    resolution = CascadeResolutionConfig(statement_function_resolution_mode="stage_resolver")
    unresolved, reasons = cascade_stage_unresolved_clause_ids(
        [clause()],
        [],
        stage_clause_ids=("one",),
        previous_reasons={"one": ("statement_function_resolver_confidence",)},
        resolution=resolution,
    )
    assert unresolved == ("one",)
    unresolved, reasons = cascade_stage_unresolved_clause_ids(
        [clause()],
        [clause(confidence=0.5)],
        stage_clause_ids=("one",),
        previous_reasons=reasons,
        resolution=resolution,
    )
    assert reasons == {"one": ("statement_function_resolver_confidence",)}
    unresolved, reasons = cascade_stage_unresolved_clause_ids(
        [clause()],
        [clause()],
        stage_clause_ids=("one",),
        previous_reasons=reasons,
        resolution=resolution,
    )
    assert unresolved == ()
    assert reasons == {"one": ()}


def test_first_evidence_after_missing_initial_result_checks_and_captures_all_dimensions() -> None:
    resolution = CascadeResolutionConfig()
    recovered = clause().model_copy(update={"knowledge_kind_decision_confidence": 0.5})
    resolution = resolution.model_copy(update={"minimum_knowledge_kind_confidence": 0.6})
    _, reasons = cascade_stage_unresolved_clause_ids(
        [recovered],
        [recovered],
        stage_clause_ids=("one",),
        previous_reasons={"one": ("no_consensus_result",)},
        resolution=resolution,
    )
    assert reasons == {"one": ("knowledge_kind_confidence",)}
    capture = capture_resolved_dimensions(
        cumulative_clause=recovered,
        stage_clause=recovered,
        previous_reasons=("no_consensus_result",),
        remaining_reasons=reasons["one"],
        source="intermediate",
        resolution=resolution,
    )
    assert set(capture) == {"statement_function", "applicability", "role_relation"}


def test_previously_accepted_dimensions_are_not_reopened_after_a_missing_stage_record() -> None:
    unresolved, reasons = cascade_stage_unresolved_clause_ids(
        [clause(confidence=0.1)],
        [clause(confidence=0.1)],
        stage_clause_ids=("one",),
        previous_reasons={"one": ("missing_stage_consensus_result",)},
        resolution=CascadeResolutionConfig(),
    )
    assert unresolved == ()
    assert reasons == {"one": ()}


def test_role_counters_and_reason_dimensions_use_canonical_name() -> None:
    counts = resolution_counts({"one": {"role_relation": {"present": False}}})
    assert counts["role_relation"] == 1
    assert "responsibility" not in counts
    assert _cascade_reason_dimensions(("role_semantics_evidence_conflict",)) == {"role_relation"}
    assert _cascade_reason_dimensions(("insufficient_applicability_presence_models",)) == {
        "applicability"
    }


def test_missing_accounting_entry_is_rejected() -> None:
    with pytest.raises(ValueError, match="every entered clause"):
        stage_accounting(clause_ids=("one", "two"), reasons={"one": ()}, selected_count=2)
