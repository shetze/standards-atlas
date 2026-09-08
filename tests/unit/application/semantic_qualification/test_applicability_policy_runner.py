from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailClauseResult,
    ApplicabilityDetailEnrichmentReport,
    ApplicabilityDetailFailure,
    ApplicabilityDetailGenerator,
    ApplicabilityDetailOutcome,
    ApplicabilityDetailRunStatistics,
    ApplicabilityDetailSelection,
    ApplicabilityDetailSelectionClause,
)
from standards_atlas.application.semantic_qualification.applicability_policy_runner import (
    CONFIRMATION_PROMPT_VERSION,
    CONFIRMATION_TASK_VERSION,
    PRIMARY_PROMPT_VERSION,
    PRIMARY_TASK_VERSION,
    RESCUE_PROMPT_VERSION,
    RESCUE_TASK_VERSION,
    applicability_policy_inference_required,
    run_applicability_policy,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
    OverallConsensusStatus,
)
from standards_atlas.domain.model import ApplicabilityTarget

NOW = datetime(2026, 9, 8, tzinfo=UTC)
MODEL_ID = "mistral-small"
MODEL_REF = "mistral/model"


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _example(index: int) -> EvaluationExample:
    text = f"Clause {index}"
    return EvaluationExample(
        id=f"example-{index}",
        input={
            "content": {"text": text, "hash": _hash(text)},
            "context": {"document_key": "DOC", "clause_id": f"clause-{index}"},
        },
        expected={},
    )


def _selection(count: int) -> ApplicabilityDetailSelection:
    clauses = tuple(
        ApplicabilityDetailSelectionClause(
            example_id=f"example-{index}",
            document_key="DOC",
            clause_id=f"clause-{index}",
            content_hash=_hash(f"Clause {index}"),
            reference=str(index),
            presence_confidence=1.0,
            presence_category="unanimous",
            presence_resolution_source="final-escalation",
        )
        for index in range(1, count + 1)
    )
    return ApplicabilityDetailSelection(
        task_version="1.0.0",
        source_matrix_id="matrix-v1",
        source_corpus_id="semantic-profile-v1",
        source_selection_sha256="a" * 64,
        source_consensus_sha256="b" * 64,
        source_coverage_sha256="c" * 64,
        source_selected_clause_count=count,
        source_qualified_clause_count=count,
        source_unqualified_clause_count=0,
        source_consensus_clause_count=count,
        selected_clause_count=count,
        clauses=clauses,
    )


def _consensus(count: int) -> ConsensusReport:
    clauses = tuple(
        ClauseConsensus(
            clause_id=f"clause-{index}",
            document_key="DOC",
            reference=str(index),
            category=ConsensusCategory.UNANIMOUS,
            applicability_category=ConsensusCategory.UNANIMOUS,
            overall_status=OverallConsensusStatus.RESOLVED,
            applicability_present=True,
            confidence=1.0,
            applicability_confidence=1.0,
            applicability_presence_confidence=1.0,
            applicability_decision_confidence=1.0,
            participating_models=3,
            applicability_participating_models=3,
            requires_review=False,
            resolution_sources={"applicability": "final-escalation"},
        )
        for index in range(1, count + 1)
    )
    return ConsensusReport(
        matrix_id="matrix-v1",
        corpus_id="semantic-profile-v1",
        prompt_id="applicability-presence",
        reasoning_mode_id="disabled",
        generated_at=NOW,
        model_count=3,
        clause_count=count,
        categories={"unanimous": count},
        review_count=0,
        clauses=clauses,
    )


def _result(
    selected: ApplicabilityDetailSelectionClause,
    value: bool | None,
    *,
    task_version: str,
    prompt_version: str,
) -> ApplicabilityDetailClauseResult:
    if value is None:
        return ApplicabilityDetailClauseResult(
            example_id=selected.example_id,
            document_key=selected.document_key,
            clause_id=selected.clause_id,
            content_hash=selected.content_hash,
            reference=selected.reference,
            presence_confidence=selected.presence_confidence,
            outcome=ApplicabilityDetailOutcome.FAILED,
            failure=ApplicabilityDetailFailure(
                error_type="LlmResponseError",
                message="truncated",
                category="invalid_response",
                finish_reason="length",
            ),
        )
    generator = ApplicabilityDetailGenerator(
        model_id=MODEL_ID,
        model=MODEL_REF,
        provider="fake",
        task_version=task_version,
        prompt_version=prompt_version,
        input_hash="input",
        raw_response_hash="response",
        duration_ms=1,
        generated_at=NOW,
    )
    if task_version == "2.0.0":
        return ApplicabilityDetailClauseResult(
            example_id=selected.example_id,
            document_key=selected.document_key,
            clause_id=selected.clause_id,
            content_hash=selected.content_hash,
            reference=selected.reference,
            presence_confidence=selected.presence_confidence,
            outcome=(
                ApplicabilityDetailOutcome.UNRESOLVED
                if value
                else ApplicabilityDetailOutcome.NOT_CONFIRMED
            ),
            applicability_target=(
                ApplicabilityTarget.CLAUSE_OR_REQUIREMENT if value else ApplicabilityTarget.NONE
            ),
            contains_clause_or_requirement_applicability=value,
            evidence_grounded=not value,
            generator=generator,
        )
    return ApplicabilityDetailClauseResult(
        example_id=selected.example_id,
        document_key=selected.document_key,
        clause_id=selected.clause_id,
        content_hash=selected.content_hash,
        reference=selected.reference,
        presence_confidence=selected.presence_confidence,
        outcome=(
            ApplicabilityDetailOutcome.UNRESOLVED
            if value
            else ApplicabilityDetailOutcome.NOT_CONFIRMED
        ),
        applicability_target=(
            ApplicabilityTarget.CLAUSE_OR_REQUIREMENT
            if value
            else ApplicabilityTarget.METHOD_OR_TECHNIQUE
        ),
        evidence_grounded=not value,
        generator=generator,
    )


class FakeService:
    def __init__(
        self,
        decisions: dict[str, bool | None],
        *,
        task_version: str,
        prompt_version: str,
    ) -> None:
        self.decisions = decisions
        self.task_version = task_version
        self.prompt_version = prompt_version
        self.selections: list[tuple[str, ...]] = []

    def pending_clause_count(self, *, selection, existing=None, fresh=False):
        if existing is None:
            return selection.selected_clause_count
        existing_coordinates = {(item.document_key, item.clause_id) for item in existing.clauses}
        return sum(
            (item.document_key, item.clause_id) not in existing_coordinates
            for item in selection.clauses
        )

    def enrich(self, *, selection, examples, existing=None, fresh=False, checkpoint=None):
        self.selections.append(tuple(item.clause_id for item in selection.clauses))
        existing_by_coordinate = {
            (item.document_key, item.clause_id): item
            for item in (existing.clauses if existing is not None else ())
        }
        results = []
        attempted = 0
        reused = 0
        for selected in selection.clauses:
            coordinate = (selected.document_key, selected.clause_id)
            if coordinate in existing_by_coordinate:
                results.append(existing_by_coordinate[coordinate])
                reused += 1
            else:
                results.append(
                    _result(
                        selected,
                        self.decisions[selected.clause_id],
                        task_version=self.task_version,
                        prompt_version=self.prompt_version,
                    )
                )
                attempted += 1
        report = ApplicabilityDetailEnrichmentReport(
            task_version=self.task_version,
            prompt_version=self.prompt_version,
            model_id=MODEL_ID,
            model_ref=MODEL_REF,
            selection_sha256=selection.fingerprint,
            config_sha256="d" * 64,
            generated_at=NOW,
            selected_clause_count=selection.selected_clause_count,
            processed_clause_count=len(results),
            enriched_clause_count=0,
            not_confirmed_clause_count=sum(
                item.outcome is ApplicabilityDetailOutcome.NOT_CONFIRMED for item in results
            ),
            unresolved_clause_count=sum(
                item.outcome is ApplicabilityDetailOutcome.UNRESOLVED for item in results
            ),
            failed_clause_count=sum(
                item.outcome is ApplicabilityDetailOutcome.FAILED for item in results
            ),
            run_statistics=ApplicabilityDetailRunStatistics(
                attempted_clause_count=attempted,
                reused_clause_count=reused,
                fresh_prediction_count=attempted,
                cached_prediction_count=0,
            ),
            clauses=tuple(results),
        )
        if checkpoint is not None:
            checkpoint(report)
        return report


def test_selective_runner_routes_only_policy_relevant_clauses() -> None:
    selection = _selection(5)
    examples = tuple(_example(index) for index in range(1, 6))
    primary = FakeService(
        {
            "clause-1": True,
            "clause-2": False,
            "clause-3": False,
            "clause-4": False,
            "clause-5": None,
        },
        task_version=PRIMARY_TASK_VERSION,
        prompt_version=PRIMARY_PROMPT_VERSION,
    )
    rescue = FakeService(
        {
            "clause-2": False,
            "clause-3": True,
            "clause-4": None,
            "clause-5": None,
        },
        task_version=RESCUE_TASK_VERSION,
        prompt_version=RESCUE_PROMPT_VERSION,
    )
    confirmation = FakeService(
        {"clause-3": True, "clause-4": False},
        task_version=CONFIRMATION_TASK_VERSION,
        prompt_version=CONFIRMATION_PROMPT_VERSION,
    )

    result = run_applicability_policy(
        selection=selection,
        consensus=_consensus(5),
        examples=examples,
        primary_service=primary,
        rescue_service=rescue,
        confirmation_service=confirmation,
    )

    assert primary.selections == [("clause-1", "clause-2", "clause-3", "clause-4", "clause-5")]
    assert rescue.selections == [("clause-2", "clause-3", "clause-4", "clause-5")]
    assert confirmation.selections == [("clause-3", "clause-4")]
    assert [stage.selected_clause_count for stage in result.report.stages] == [5, 4, 2]
    assert [case.final_present for case in result.report.cases] == [True, False, True, False, None]
    assert [case.confirmation_selected for case in result.report.cases] == [
        False,
        False,
        True,
        True,
        False,
    ]


def test_selective_runner_reuses_complete_role_reports_on_resume() -> None:
    selection = _selection(2)
    examples = (_example(1), _example(2))
    primary = FakeService(
        {"clause-1": True, "clause-2": False},
        task_version=PRIMARY_TASK_VERSION,
        prompt_version=PRIMARY_PROMPT_VERSION,
    )
    rescue = FakeService(
        {"clause-2": False},
        task_version=RESCUE_TASK_VERSION,
        prompt_version=RESCUE_PROMPT_VERSION,
    )
    confirmation = FakeService(
        {},
        task_version=CONFIRMATION_TASK_VERSION,
        prompt_version=CONFIRMATION_PROMPT_VERSION,
    )
    assert applicability_policy_inference_required(
        selection=selection,
        primary_service=primary,
        rescue_service=rescue,
        confirmation_service=confirmation,
    )
    first = run_applicability_policy(
        selection=selection,
        consensus=_consensus(2),
        examples=examples,
        primary_service=primary,
        rescue_service=rescue,
        confirmation_service=confirmation,
    )
    assert not applicability_policy_inference_required(
        selection=selection,
        primary_service=primary,
        rescue_service=rescue,
        confirmation_service=confirmation,
        existing_primary=first.reports["primary"],
        existing_rescue=first.reports["rescue"],
        existing_confirmation=first.reports["confirmation"],
    )

    resumed = run_applicability_policy(
        selection=selection,
        consensus=_consensus(2),
        examples=examples,
        primary_service=primary,
        rescue_service=rescue,
        confirmation_service=confirmation,
        existing_primary=first.reports["primary"],
        existing_rescue=first.reports["rescue"],
        existing_confirmation=first.reports["confirmation"],
    )

    assert [stage.pending_clause_count for stage in resumed.report.stages] == [0, 0, 0]
    assert [stage.reused_clause_count for stage in resumed.report.stages] == [2, 1, 0]
    assert [case.final_present for case in resumed.report.cases] == [True, False]
