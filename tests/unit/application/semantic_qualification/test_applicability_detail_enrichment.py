from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.ports.llm_gateway import (
    LlmHealth,
    LlmUnavailableError,
    StructuredGenerationResult,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailEnrichmentConfig,
    ApplicabilityDetailEnrichmentService,
    ApplicabilityDetailFailureReport,
    ApplicabilityDetailOutcome,
    build_applicability_detail_selection,
    validate_applicability_detail_artifacts,
    validate_completed_applicability_detail_enrichment,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
    OverallConsensusStatus,
)
from standards_atlas.application.semantic_qualification.proposals import SemanticTaskRepository
from standards_atlas.application.semantic_qualification.qualification_coverage import (
    build_qualification_coverage,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
    QualificationSelectionClause,
)

RESOURCES = Path("src/standards_atlas/resources/semantic")


class SequenceGateway:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.requests = []

    def health(self) -> LlmHealth:
        return LlmHealth(True, ("model-ref",))

    def generate_structured(self, request):
        self.calls += 1
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return StructuredGenerationResult(
            value=response,
            model=request.model or "model-ref",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash=f"input-{self.calls}",
            raw_response_hash=f"response-{self.calls}",
            duration_ms=10,
            cached=False,
            raw_response={"value": response},
        )


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _example(index: int, text: str) -> EvaluationExample:
    return EvaluationExample(
        id=f"example-{index}",
        input={
            "content": {"text": text, "hash": _hash(text)},
            "context": {
                "document_key": "DOC",
                "clause_id": f"clause-{index}",
                "reference": f"{index}",
                "title": f"Clause {index}",
            },
        },
        expected={},
    )


def _selection(count: int) -> QualificationRunSelection:
    clauses = tuple(
        QualificationSelectionClause(
            example_id=f"example-{index}",
            document_key="DOC",
            clause_id=f"clause-{index}",
        )
        for index in range(1, count + 1)
    )
    return QualificationRunSelection(
        task="semantic-profile-classification",
        dataset_version="2.2.0",
        corpus_id="semantic-profile-v1",
        dataset_sha256="a" * 64,
        corpus_sha256="b" * 64,
        dataset_clause_count=count,
        corpus_clause_count=count,
        selected_clause_count=count,
        clauses=clauses,
    )


def _consensus(*presence: bool) -> ConsensusReport:
    clauses = tuple(
        ClauseConsensus(
            clause_id=f"clause-{index}",
            document_key="DOC",
            reference=f"{index}",
            heading=f"Clause {index}",
            category=ConsensusCategory.UNANIMOUS,
            applicability_category=ConsensusCategory.UNANIMOUS,
            overall_status=OverallConsensusStatus.RESOLVED,
            applicability_present=value,
            confidence=1.0,
            applicability_confidence=1.0,
            applicability_presence_confidence=1.0,
            applicability_decision_confidence=1.0,
            participating_models=3,
            applicability_participating_models=3,
            requires_review=False,
            resolution_sources={"applicability": "final-escalation"},
        )
        for index, value in enumerate(presence, start=1)
    )
    return ConsensusReport(
        matrix_id="matrix-v1",
        corpus_id="semantic-profile-v1",
        prompt_id="applicability-presence",
        reasoning_mode_id="disabled",
        generated_at=datetime.now(UTC),
        model_count=3,
        clause_count=len(clauses),
        categories={"unanimous": len(clauses)},
        review_count=0,
        clauses=clauses,
    )


def _detail_selection(
    *,
    examples: tuple[EvaluationExample, ...],
    consensus: ConsensusReport,
    run_selection: QualificationRunSelection | None = None,
):
    persisted_selection = run_selection or _selection(len(examples))
    return build_applicability_detail_selection(
        run_selection=persisted_selection,
        examples=examples,
        consensus=consensus,
        coverage=build_qualification_coverage(
            selection=persisted_selection,
            report=consensus,
        ),
        task_version="1.0.0",
    )


def _service(gateway: SequenceGateway, artifact_root: Path | None = None):
    task, schema = SemanticTaskRepository(RESOURCES / "tasks").load(
        "applicability-detail-enrichment", "1.0.0"
    )
    assert task.applicability_taxonomy
    prompt = PromptRepository(RESOURCES / "prompts").load(
        "applicability-detail-enrichment", "detail-structure-aware-v1"
    )
    config = ApplicabilityDetailEnrichmentConfig(
        enabled=True,
        model="detail-model",
        retry_attempts=1,
        retry_backoff_seconds=0,
    )
    return ApplicabilityDetailEnrichmentService(
        gateway,
        config=config,
        prompt=prompt,
        canonical_schema=schema,
        model_id="detail-model",
        model_ref="model-ref",
        artifact_root=artifact_root,
    )


def test_selection_contains_only_final_presence_positive_clauses() -> None:
    examples = (
        _example(1, "This clause applies to onboard equipment."),
        _example(2, "The supplier records the result."),
        _example(3, "These requirements apply to the referenced subsystem."),
    )

    selected = _detail_selection(
        examples=examples,
        consensus=_consensus(True, False, True),
    )

    assert selected.selected_clause_count == 2
    assert selected.source_selected_clause_count == 3
    assert selected.source_qualified_clause_count == 3
    assert selected.source_unqualified_clause_count == 0
    assert selected.source_consensus_clause_count == 3
    assert [item.clause_id for item in selected.clauses] == ["clause-1", "clause-3"]
    assert all(item.presence_resolution_source == "final-escalation" for item in selected.clauses)


def test_selection_rejects_missing_consensus_for_qualified_clause() -> None:
    examples = (
        _example(1, "This clause applies to onboard equipment."),
        _example(2, "The supplier records the result."),
    )
    run_selection = _selection(2)
    complete_consensus = _consensus(True, False)
    coverage = build_qualification_coverage(
        selection=run_selection,
        report=complete_consensus,
    )
    incomplete_consensus = complete_consensus.model_copy(
        update={
            "clause_count": 1,
            "clauses": complete_consensus.clauses[:1],
        }
    )

    with pytest.raises(
        ValueError,
        match="final consensus coordinates differ from qualified coverage: missing=1",
    ):
        build_applicability_detail_selection(
            run_selection=run_selection,
            examples=examples,
            consensus=incomplete_consensus,
            coverage=coverage,
            task_version="1.0.0",
        )


def test_selection_accepts_clause_explicitly_marked_unqualified() -> None:
    examples = (
        _example(1, "This clause applies to onboard equipment."),
        _example(2, "The supplier records the result."),
    )
    run_selection = _selection(2)
    consensus = _consensus(True).model_copy(update={"clause_count": 1})
    coverage = build_qualification_coverage(selection=run_selection, report=consensus)

    selected = build_applicability_detail_selection(
        run_selection=run_selection,
        examples=examples,
        consensus=consensus,
        coverage=coverage,
        task_version="1.0.0",
    )

    assert selected.selected_clause_count == 1
    assert selected.source_consensus_clause_count == 1
    assert selected.source_qualified_clause_count == 1
    assert selected.source_unqualified_clause_count == 1


def test_sparse_enrichment_classifies_grounded_unresolved_and_empty_details(
    tmp_path: Path,
) -> None:
    texts = (
        "These requirements apply to new systems.",
        "Applicability is described in the referenced clause.",
        "The clause applies to legacy systems.",
    )
    examples = tuple(_example(index, text) for index, text in enumerate(texts, start=1))
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True, True, True),
    )
    gateway = SequenceGateway(
        {
            "applicability_statement_confirmed": True,
            "applicability_functions": ["inclusion"],
            "evidence": [
                {"function": "inclusion", "text": "apply to new systems"},
            ],
        },
        {
            "applicability_statement_confirmed": False,
            "applicability_functions": [],
            "evidence": [],
        },
        {
            "applicability_statement_confirmed": True,
            "applicability_functions": ["inclusion"],
            "evidence": [
                {"function": "inclusion", "text": "apply to future systems"},
            ],
        },
    )

    report = _service(gateway, tmp_path / "artifacts").enrich(
        selection=selection,
        examples=examples,
    )

    assert gateway.calls == 3
    assert [item.outcome for item in report.clauses] == [
        ApplicabilityDetailOutcome.ENRICHED,
        ApplicabilityDetailOutcome.NOT_CONFIRMED,
        ApplicabilityDetailOutcome.UNRESOLVED,
    ]
    assert report.enriched_clause_count == 1
    assert report.not_confirmed_clause_count == 1
    assert report.unresolved_clause_count == 1
    assert report.failed_clause_count == 0
    assert (tmp_path / "artifacts" / "clauses" / "example-1" / "request.json").is_file()
    assert (tmp_path / "artifacts" / "clauses" / "example-1" / "response.json").is_file()


def test_resume_reuses_completed_results_and_retries_only_failures() -> None:
    examples = (
        _example(1, "These requirements apply to new systems."),
        _example(2, "This clause applies when the safety function is active."),
    )
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True, True),
    )
    first_gateway = SequenceGateway(
        {
            "applicability_statement_confirmed": True,
            "applicability_functions": ["inclusion"],
            "evidence": [{"function": "inclusion", "text": "new systems"}],
        },
        LlmUnavailableError("temporary outage"),
    )
    first = _service(first_gateway).enrich(selection=selection, examples=examples)
    assert first.enriched_clause_count == 1
    assert first.failed_clause_count == 1

    second_gateway = SequenceGateway(
        {
            "applicability_statement_confirmed": True,
            "applicability_functions": ["applicability_condition"],
            "evidence": [
                {
                    "function": "applicability_condition",
                    "text": "when the safety function is active",
                }
            ],
        }
    )
    service = _service(second_gateway)
    assert service.pending_clause_count(selection=selection, existing=first) == 1
    resumed = service.enrich(
        selection=selection,
        examples=examples,
        existing=first,
    )

    assert service.pending_clause_count(selection=selection, existing=resumed) == 0
    assert second_gateway.calls == 1
    assert resumed.failed_clause_count == 0
    assert resumed.enriched_clause_count == 2
    assert resumed.run_statistics.reused_clause_count == 1
    assert resumed.run_statistics.attempted_clause_count == 1


def test_global_review_status_does_not_filter_final_presence_positive_clause() -> None:
    examples = (_example(1, "These requirements apply to new systems."),)
    consensus = _consensus(True)
    reviewed_clause = consensus.clauses[0].model_copy(
        update={
            "requires_review": True,
            "review_reasons": ("role_relation_disagreement",),
        }
    )
    reviewed_consensus = consensus.model_copy(
        update={
            "review_count": 1,
            "clauses": (reviewed_clause,),
        }
    )

    selection = _detail_selection(
        examples=examples,
        consensus=reviewed_consensus,
    )

    assert selection.selected_clause_count == 1
    assert selection.clauses[0].source_requires_review is True


def test_evidence_grounding_preserves_source_case() -> None:
    text = "These Requirements apply to new systems."
    examples = (_example(1, text),)
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True),
    )
    gateway = SequenceGateway(
        {
            "applicability_statement_confirmed": True,
            "applicability_functions": ["inclusion"],
            "evidence": [{"function": "inclusion", "text": "these requirements"}],
        }
    )

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert report.clauses[0].outcome is ApplicabilityDetailOutcome.UNRESOLVED
    assert report.clauses[0].evidence_grounded is False


def test_empty_positive_selection_performs_zero_inference_calls() -> None:
    examples = (_example(1, "The supplier records the result."),)
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(False),
    )
    gateway = SequenceGateway()

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert gateway.calls == 0
    assert report.selected_clause_count == 0
    assert report.processed_clause_count == 0


def test_detail_prompt_uses_positive_instruction_framing() -> None:
    root = RESOURCES / "prompts" / "applicability-detail-enrichment" / "detail-structure-aware-v1"
    prompt_text = "\n".join(
        (root / name).read_text(encoding="utf-8").casefold() for name in ("system.txt", "user.txt")
    )

    negative_instruction_tokens = (
        " do not ",
        " don't ",
        " never ",
        " without ",
        " must not ",
        " no ",
        " cannot ",
    )
    padded = f" {prompt_text} "
    assert all(token not in padded for token in negative_instruction_tokens)


def test_detail_predictions_are_canonicalized_by_taxonomy_order() -> None:
    text = "This clause applies to the system except for legacy installations."
    examples = (_example(1, text),)
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True),
    )
    gateway = SequenceGateway(
        {
            "applicability_statement_confirmed": True,
            "applicability_functions": ["exception", "scope_definition"],
            "evidence": [
                {"function": "exception", "text": "except for legacy installations"},
                {"function": "scope_definition", "text": "applies to the system"},
            ],
        }
    )

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert [item.value for item in report.clauses[0].applicability_functions] == [
        "scope_definition",
        "exception",
    ]
    assert [item.function.value for item in report.clauses[0].evidence] == [
        "scope_definition",
        "exception",
    ]


def test_confirmed_statement_with_open_detail_is_unresolved() -> None:
    examples = (_example(1, "This clause applies to the referenced case."),)
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True),
    )
    gateway = SequenceGateway(
        {
            "applicability_statement_confirmed": True,
            "applicability_functions": [],
            "evidence": [],
        }
    )

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert report.clauses[0].outcome is ApplicabilityDetailOutcome.UNRESOLVED
    assert report.clauses[0].applicability_statement_confirmed is True


def test_selection_rejects_content_hash_mismatch() -> None:
    example = _example(1, "This clause applies to the system.")
    corrupted = EvaluationExample(
        id=example.id,
        input={
            "content": {"text": "This clause applies to the system.", "hash": "sha256:" + "0" * 64},
            "context": example.input["context"],
        },
        expected={},
    )

    with pytest.raises(ValueError, match="content hash differs"):
        _detail_selection(
            examples=(corrupted,),
            consensus=_consensus(True),
        )


def test_completed_detail_enrichment_is_validated_for_archival() -> None:
    examples = (_example(1, "These requirements apply to new systems."),)
    selection = _detail_selection(examples=examples, consensus=_consensus(True))
    gateway = SequenceGateway(
        {
            "applicability_statement_confirmed": True,
            "applicability_functions": ["inclusion"],
            "evidence": [{"function": "inclusion", "text": "apply to new systems"}],
        }
    )
    report = _service(gateway).enrich(selection=selection, examples=examples)
    failures = ApplicabilityDetailFailureReport(
        selection_sha256=report.selection_sha256,
        failed_clause_count=0,
        clauses=(),
    )
    config = ApplicabilityDetailEnrichmentConfig(
        enabled=True,
        model="detail-model",
        retry_attempts=1,
        retry_backoff_seconds=0,
    )

    summary = validate_completed_applicability_detail_enrichment(
        expected_selection=selection,
        persisted_selection=selection,
        report=report,
        failures=failures,
        config=config,
        model_id="detail-model",
        model_ref="model-ref",
    )

    assert summary.complete is True
    assert summary.selected_clause_count == 1
    assert summary.processed_clause_count == 1
    assert summary.enriched_clause_count == 1
    assert summary.failed_clause_count == 0
    assert summary.selection_sha256 == selection.fingerprint
    assert summary.config_sha256 == config.fingerprint


def test_archival_rejects_checkpoint_before_all_detail_clauses_are_processed() -> None:
    examples = (
        _example(1, "These requirements apply to new systems."),
        _example(2, "This clause applies when the safety function is active."),
    )
    selection = _detail_selection(examples=examples, consensus=_consensus(True, True))
    gateway = SequenceGateway(
        {
            "applicability_statement_confirmed": True,
            "applicability_functions": ["inclusion"],
            "evidence": [{"function": "inclusion", "text": "new systems"}],
        },
        {
            "applicability_statement_confirmed": True,
            "applicability_functions": ["applicability_condition"],
            "evidence": [
                {
                    "function": "applicability_condition",
                    "text": "when the safety function is active",
                }
            ],
        },
    )
    checkpoints = []
    _service(gateway).enrich(
        selection=selection,
        examples=examples,
        checkpoint=checkpoints.append,
    )
    partial = checkpoints[0]
    failures = ApplicabilityDetailFailureReport(
        selection_sha256=partial.selection_sha256,
        failed_clause_count=0,
        clauses=(),
    )
    config = ApplicabilityDetailEnrichmentConfig(
        enabled=True,
        model="detail-model",
        retry_attempts=1,
        retry_backoff_seconds=0,
    )

    with pytest.raises(ValueError, match="enrichment is incomplete: 1/2 clauses"):
        validate_completed_applicability_detail_enrichment(
            expected_selection=selection,
            persisted_selection=selection,
            report=partial,
            failures=failures,
            config=config,
            model_id="detail-model",
            model_ref="model-ref",
        )


def test_archival_rejects_detail_selection_from_outdated_presence_consensus() -> None:
    examples = (_example(1, "These requirements apply to new systems."),)
    selection = _detail_selection(examples=examples, consensus=_consensus(True))
    gateway = SequenceGateway(
        {
            "applicability_statement_confirmed": False,
            "applicability_functions": [],
            "evidence": [],
        }
    )
    report = _service(gateway).enrich(selection=selection, examples=examples)
    failures = ApplicabilityDetailFailureReport(
        selection_sha256=report.selection_sha256,
        failed_clause_count=0,
        clauses=(),
    )
    config = ApplicabilityDetailEnrichmentConfig(
        enabled=True,
        model="detail-model",
        retry_attempts=1,
        retry_backoff_seconds=0,
    )
    outdated = selection.model_copy(update={"source_consensus_sha256": "0" * 64})

    with pytest.raises(ValueError, match="differs from the current final Presence consensus"):
        validate_completed_applicability_detail_enrichment(
            expected_selection=selection,
            persisted_selection=outdated,
            report=report,
            failures=failures,
            config=config,
            model_id="detail-model",
            model_ref="model-ref",
        )


def test_archival_validates_clause_local_detail_evidence(tmp_path: Path) -> None:
    examples = (_example(1, "These requirements apply to new systems."),)
    selection = _detail_selection(examples=examples, consensus=_consensus(True))
    artifact_root = tmp_path / "applicability-detail"
    gateway = SequenceGateway(
        {
            "applicability_statement_confirmed": True,
            "applicability_functions": ["inclusion"],
            "evidence": [{"function": "inclusion", "text": "apply to new systems"}],
        }
    )
    report = _service(gateway, artifact_root=artifact_root).enrich(
        selection=selection,
        examples=examples,
    )

    validate_applicability_detail_artifacts(
        artifact_root=artifact_root,
        selection=selection,
        report=report,
    )

    (artifact_root / "clauses" / "example-1" / "response.json").unlink()
    with pytest.raises(ValueError, match="response for example-1 not found"):
        validate_applicability_detail_artifacts(
            artifact_root=artifact_root,
            selection=selection,
            report=report,
        )


def test_archival_rejects_unreferenced_detail_clause_artifacts(tmp_path: Path) -> None:
    artifact_root = tmp_path / "applicability-detail"
    artifact_root.mkdir()
    (artifact_root / "clauses" / "stale-example").mkdir(parents=True)
    examples: tuple[EvaluationExample, ...] = ()
    selection = _detail_selection(examples=examples, consensus=_consensus())
    report = _service(SequenceGateway(), artifact_root=artifact_root).enrich(
        selection=selection,
        examples=examples,
    )

    with pytest.raises(ValueError, match="clause artifacts differ.*unexpected=1"):
        validate_applicability_detail_artifacts(
            artifact_root=artifact_root,
            selection=selection,
            report=report,
        )


def test_failed_detail_clause_may_archive_raw_response_and_failure(tmp_path: Path) -> None:
    examples = (_example(1, "These requirements apply to new systems."),)
    selection = _detail_selection(examples=examples, consensus=_consensus(True))
    artifact_root = tmp_path / "applicability-detail"
    report = _service(
        SequenceGateway({"unexpected": "response"}),
        artifact_root=artifact_root,
    ).enrich(selection=selection, examples=examples)

    assert report.clauses[0].outcome is ApplicabilityDetailOutcome.FAILED
    assert (artifact_root / "clauses" / "example-1" / "response.json").is_file()
    assert (artifact_root / "clauses" / "example-1" / "failure.json").is_file()
    validate_applicability_detail_artifacts(
        artifact_root=artifact_root,
        selection=selection,
        report=report,
    )
