from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from standards_atlas.adapters.filesystem.assertion_experiment_repository import (
    FileSystemAssertionExperimentRepository,
)
from standards_atlas.adapters.filesystem.context_source_package_repository import (
    FileSystemContextSourcePackageRepository,
)
from standards_atlas.application.assertion_qualification import (
    load_assertion_experiment_baseline_report,
)
from standards_atlas.application.assertion_qualification.experiment import (
    AssertionExperimentService,
    ExperimentAttemptStatus,
    ExperimentBindingError,
    ExperimentBudget,
    evaluate_assertion_experiment,
    plan_assertion_experiment,
)
from standards_atlas.application.assertion_qualification.models import (
    AssertionAuditBinding,
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
)
from standards_atlas.application.ports.llm_gateway import (
    LlmHealth,
    LlmResponseError,
    LlmTimeoutError,
    StructuredGenerationResult,
    TokenUsage,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TextBlock,
)

TEXT = "A verification activity is described."


def _document() -> EngineeringDocument:
    clause = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="TEST", clause="1"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="t1", text=TEXT),),
    )
    return EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )


def _suite() -> AssertionGoldenSuite:
    return AssertionGoldenSuite(
        id="dev",
        version="1.0.0",
        partition=AssertionGoldenPartition.DEVELOPMENT,
        audit=AssertionAuditBinding(review_id="r", review_version="1", audit_sha256="a" * 64),
        ontology_versions=("standards-atlas-core@2.0.0",),
        cases=(
            AssertionGoldenCase(
                source_document_key="TEST",
                clause_id=ClauseId(value="c1"),
                reference="TEST:1",
                canonical_reference="TEST 1",
                text_sha256=hashlib.sha256(TEXT.encode()).hexdigest(),
                source_sha256="b" * 64,
                entities=(),
                assertions=(),
            ),
        ),
    )


class _Gateway:
    provider = "fake"

    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or ["ok"])
        self.calls = 0

    def health(self):
        return LlmHealth(available=True, models=("fake",))

    def generate_structured(self, request):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if outcome == "timeout":
            raise LlmTimeoutError("synthetic timeout")
        if outcome == "response_error_with_usage":
            raise LlmResponseError(
                "synthetic truncated response",
                raw_content="{",
                raw_response={
                    "model": "fake-effective",
                    "usage": {
                        "prompt_tokens": 6,
                        "completion_tokens": 4,
                        "total_tokens": 10,
                    },
                },
                finish_reason="length",
            )
        if outcome == "interrupt":
            raise KeyboardInterrupt("synthetic interruption")
        cached = outcome == "cached"
        return StructuredGenerationResult(
            value={"entities": [], "assertions": []},
            model="fake-effective",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash=f"{self.calls:064x}",
            raw_response_hash=f"{self.calls + 10:064x}",
            duration_ms=7,
            usage=TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
            cached=cached,
            raw_response={"synthetic": True, "call": self.calls},
        )


def _extractor_factory(gateway, manifest):
    from standards_atlas.adapters.llm import OntologyGuidedKnowledgeProposalExtractor

    return OntologyGuidedKnowledgeProposalExtractor(
        gateway,
        model=manifest.requested_model,
        provider="fake",
        prompt_version=manifest.prompt_version,
        task_schema_version=manifest.task_schema_version,
        temperature=manifest.temperature,
        seed=manifest.seed,
        max_tokens=manifest.max_output_tokens_per_call,
        reasoning_enabled=manifest.reasoning_enabled,
    )


def _two_case_document_and_suite() -> tuple[EngineeringDocument, AssertionGoldenSuite]:
    clauses = (
        Clause(
            id=ClauseId(value="c1"),
            reference=StandardReference(standard="TEST", clause="1"),
            clause_type=ClauseType.CLAUSE,
            content=(TextBlock(id="t1", text=TEXT),),
        ),
        Clause(
            id=ClauseId(value="c2"),
            reference=StandardReference(standard="TEST", clause="2"),
            clause_type=ClauseType.CLAUSE,
            content=(TextBlock(id="t2", text=TEXT),),
        ),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=clauses,
    )
    cases = tuple(
        AssertionGoldenCase(
            source_document_key="TEST",
            clause_id=clause.id,
            reference=f"TEST:{index}",
            canonical_reference=f"TEST {index}",
            text_sha256=hashlib.sha256(TEXT.encode()).hexdigest(),
            source_sha256=("b" if index == 1 else "d") * 64,
            entities=(),
            assertions=(),
        )
        for index, clause in enumerate(clauses, start=1)
    )
    suite = AssertionGoldenSuite(
        id="dev-two",
        version="1.0.0",
        partition=AssertionGoldenPartition.DEVELOPMENT,
        audit=AssertionAuditBinding(review_id="r", review_version="1", audit_sha256="a" * 64),
        ontology_versions=("standards-atlas-core@2.0.0",),
        cases=cases,
    )
    return document, suite


def _planned(tmp_path: Path, *, gateway=None, max_calls=1, retries=0, repetitions=1):
    suite = _suite()
    document = _document()
    workspace = tmp_path / ".atlas" / "data"
    source_repo = FileSystemContextSourcePackageRepository(workspace)
    manifest = plan_assertion_experiment(
        suite,
        {"TEST": document},
        experiment_id="exp-1",
        code_revision="sha256:" + "c" * 64,
        variant_id="B0",
        prompt_version="ontology-guided-assertions-source-bound-v1",
        model_route="fake",
        source_packages=source_repo,
        requested_model="fake",
        repetitions=repetitions,
        execution_authorized=True,
        authorization_reference="synthetic-test-authorization",
        budget=ExperimentBudget(max_calls=max_calls, max_retries_per_case=retries),
    )
    repo = FileSystemAssertionExperimentRepository(tmp_path, workspace)
    repo.save_manifest(manifest)
    service = AssertionExperimentService(
        repository=repo,
        source_packages=source_repo,
        gateway=gateway or _Gateway(),
        extractor_factory=_extractor_factory,
    )
    return suite, document, manifest, repo, source_repo, service


def test_plan_is_model_free_and_binds_source_package(tmp_path: Path) -> None:
    gateway = _Gateway()
    suite, _, manifest, repo, _, _ = _planned(tmp_path, gateway=gateway)

    assert gateway.calls == 0
    assert manifest.golden_suite_id == suite.id
    assert manifest.cases[0].source_package_sha256.startswith("sha256:")
    assert repo.load_manifest("exp-1") == manifest


def test_run_records_private_raw_attempt_and_resume_does_not_repeat_completed_cell(
    tmp_path: Path,
) -> None:
    gateway = _Gateway()
    suite, document, manifest, repo, _, service = _planned(tmp_path, gateway=gateway)

    state = service.run(manifest, suite, {"TEST": document})
    resumed = service.run(manifest, suite, {"TEST": document}, resume=True)

    assert gateway.calls == 1
    assert state == resumed
    assert state.attempts[0].status is ExperimentAttemptStatus.OK
    raw_path = Path(state.attempts[0].private_raw_artifact)
    assert raw_path.is_file()
    assert raw_path.stat().st_mode & 0o077 == 0
    assert state.attempts[0].effective_model == "fake-effective"
    assert state.attempts[0].usage.total_tokens == 5


def test_technical_retry_is_new_inference_and_all_attempts_remain_visible(tmp_path: Path) -> None:
    gateway = _Gateway(["timeout", "ok"])
    suite, document, manifest, _, _, service = _planned(
        tmp_path, gateway=gateway, max_calls=2, retries=1
    )

    state = service.run(manifest, suite, {"TEST": document})

    assert gateway.calls == 2
    assert [a.status for a in state.attempts] == [
        ExperimentAttemptStatus.TIMEOUT,
        ExperimentAttemptStatus.OK,
    ]
    assert len({a.attempt_id for a in state.attempts}) == 2


def test_budget_is_checked_before_call_and_blocked_cell_is_not_silently_completed(
    tmp_path: Path,
) -> None:
    gateway = _Gateway(["timeout", "ok"])
    suite, document, manifest, _, _, service = _planned(
        tmp_path, gateway=gateway, max_calls=1, retries=1
    )

    state = service.run(manifest, suite, {"TEST": document})

    assert gateway.calls == 1
    assert [a.status for a in state.attempts] == [
        ExperimentAttemptStatus.TIMEOUT,
        ExperimentAttemptStatus.BUDGET_BLOCKED,
    ]
    assert state.completed_cells == ()
    assert state.blocked_reason


def test_response_error_usage_is_recorded_and_counts_toward_next_call_budget(
    tmp_path: Path,
) -> None:
    document, suite = _two_case_document_and_suite()
    workspace = tmp_path / ".atlas" / "data"
    source_repo = FileSystemContextSourcePackageRepository(workspace)
    manifest = plan_assertion_experiment(
        suite,
        {"TEST": document},
        experiment_id="exp-error-usage",
        code_revision="sha256:" + "c" * 64,
        variant_id="B0",
        prompt_version="ontology-guided-assertions-source-bound-v1",
        model_route="fake",
        source_packages=source_repo,
        requested_model="fake",
        execution_authorized=True,
        authorization_reference="synthetic-test-authorization",
        budget=ExperimentBudget(max_calls=2, max_total_tokens=9),
    )
    repo = FileSystemAssertionExperimentRepository(tmp_path, workspace)
    repo.save_manifest(manifest)
    gateway = _Gateway(["response_error_with_usage", "ok"])
    service = AssertionExperimentService(
        repository=repo,
        source_packages=source_repo,
        gateway=gateway,
        extractor_factory=_extractor_factory,
    )

    state = service.run(manifest, suite, {"TEST": document})

    assert gateway.calls == 1
    assert [attempt.status for attempt in state.attempts] == [
        ExperimentAttemptStatus.RESPONSE_ERROR,
        ExperimentAttemptStatus.BUDGET_BLOCKED,
    ]
    assert state.attempts[0].usage is not None
    assert state.attempts[0].usage.prompt_tokens == 6
    assert state.attempts[0].usage.completion_tokens == 4
    assert state.attempts[0].usage.total_tokens == 10
    assert state.blocked_reason == "max_total_tokens exhausted before inference"


def test_changed_manifest_prevents_resume_reuse(tmp_path: Path) -> None:
    suite, document, manifest, _, _, service = _planned(tmp_path)
    service.run(manifest, suite, {"TEST": document})
    changed = manifest.model_copy(update={"prompt_version": "changed"})

    with pytest.raises(ValueError, match="manifest changed"):
        service.run(changed, suite, {"TEST": document}, resume=True)


def test_report_uses_existing_evaluator_and_keeps_failed_coverage_separate(tmp_path: Path) -> None:
    gateway = _Gateway()
    suite, document, manifest, repo, source_repo, service = _planned(tmp_path, gateway=gateway)
    state = service.run(manifest, suite, {"TEST": document})
    proposal = repo.load_proposal(state.attempts[0].proposal_run_id, "TEST")
    package = source_repo.load(manifest.cases[0].source_package_binding)

    report = evaluate_assertion_experiment(
        manifest,
        state,
        suite,
        proposals=(proposal,),
        source_packages=(package,),
    )

    assert report.qualification_report.evaluation_contract == "assertion-clause-local-v1"
    assert report.coverage.planned_cells == 1
    assert report.coverage.technically_completed_cells == 1
    assert report.stage_failures == {}
    assert report.effort.calls == 1
    assert report.effort.total_tokens == 5
    assert report.effort.monetary_cost is None


def test_baseline_loader_accepts_experiment_comparison_envelope(tmp_path: Path) -> None:
    gateway = _Gateway()
    suite, document, manifest, repo, source_repo, service = _planned(tmp_path, gateway=gateway)
    state = service.run(manifest, suite, {"TEST": document})
    proposal = repo.load_proposal(state.attempts[0].proposal_run_id, "TEST")
    package = source_repo.load(manifest.cases[0].source_package_binding)
    comparison = evaluate_assertion_experiment(
        manifest,
        state,
        suite,
        proposals=(proposal,),
        source_packages=(package,),
    )
    path = tmp_path / "comparison.json"
    path.write_text(comparison.model_dump_json(indent=2), encoding="utf-8")

    baseline = load_assertion_experiment_baseline_report(path)

    assert baseline == comparison.qualification_report


def test_cached_result_cannot_satisfy_fresh_repetition(tmp_path: Path) -> None:
    gateway = _Gateway(["cached"])
    suite, document, manifest, _, _, service = _planned(tmp_path, gateway=gateway)

    state = service.run(manifest, suite, {"TEST": document})

    assert gateway.calls == 1
    assert state.attempts[0].status is ExperimentAttemptStatus.CACHE_REPLAY_REJECTED
    assert state.completed_cells == ("r1:TEST:c1",)


def test_interrupted_call_leaves_unknown_attempt_for_safe_resume(tmp_path: Path) -> None:
    gateway = _Gateway(["interrupt"])
    suite, document, manifest, repo, _, service = _planned(tmp_path, gateway=gateway)

    with pytest.raises(KeyboardInterrupt):
        service.run(manifest, suite, {"TEST": document})

    persisted = repo.load_state(manifest.experiment_id)
    assert persisted is not None
    assert len(persisted.attempts) == 1
    assert persisted.attempts[0].status is ExperimentAttemptStatus.OUTCOME_UNKNOWN
    assert persisted.completed_cells == ()


def test_run_rejects_unapproved_plan_before_gateway_call(tmp_path: Path) -> None:
    gateway = _Gateway()
    suite, document, manifest, repo, source_repo, _ = _planned(tmp_path, gateway=gateway)
    unauthorized = manifest.model_copy(
        update={"execution_authorized": False, "authorization_reference": None}
    )
    repo.save_manifest(unauthorized)
    service = AssertionExperimentService(
        repository=repo,
        source_packages=source_repo,
        gateway=gateway,
        extractor_factory=_extractor_factory,
    )

    with pytest.raises(ExperimentBindingError, match="not authorized"):
        service.run(unauthorized, suite, {"TEST": document})

    assert gateway.calls == 0
