from datetime import UTC, datetime
from pathlib import Path

import yaml

from standards_atlas.application.semantic_qualification.annotations import (
    AnnotationGenerator,
    AnnotationLifecycleStatus,
    AnnotationReview,
    ClauseAnnotationRepository,
    ClauseEvaluationAnnotation,
    ClauseReference,
    CorpusClause,
    CorpusManifestRepository,
    EvaluationCorpusManifest,
    ReviewDecision,
    StatementFunctionSelection,
    normalized_content_hash,
)
from standards_atlas.application.semantic_qualification.prompt_comparison import (
    build_prompt_comparison_report,
    persist_prompt_comparison_report,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    MatrixObservation,
    ModelCandidate,
    PromptCandidate,
    QualificationMatrixManifest,
)
from standards_atlas.domain.model import StatementFunction


def _reference(clause_id: str, text: str) -> ClauseReference:
    return ClauseReference(
        knowledge_domain="functional-safety",
        document_key="IEC61508-3",
        clause_id=clause_id,
        content_hash=normalized_content_hash(text),
    )


def _candidate(reference: ClauseReference, role: StatementFunction) -> ClauseEvaluationAnnotation:
    return ClauseEvaluationAnnotation(
        task="semantic-profile-classification",
        lifecycle_status=AnnotationLifecycleStatus.PROPOSED,
        clause=reference,
        proposal=StatementFunctionSelection(
            statement_functions=(role,), primary_function=role, confidence=0.8
        ),
        generator=AnnotationGenerator(
            provider="local",
            model="model-a",
            prompt_id="prompt",
            generated_at=datetime(2026, 8, 30, tzinfo=UTC),
        ),
    )


def _write_prediction(run: Path, annotation: ClauseEvaluationAnnotation) -> None:
    path = run / annotation.clause.document_key / annotation.clause.clause_id / "evaluation.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"annotation_candidate": annotation.model_dump(mode="json", exclude_none=True)},
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _manifest(tmp_path: Path, baseline_run: Path, context_run: Path) -> QualificationMatrixManifest:
    prompts = tuple(
        PromptCandidate(id=prompt_id)
        for prompt_id in (
            "content-only",
            "structure-aware",
            "reference-aware",
            "bounded-reasoning",
        )
    )
    observations = (
        MatrixObservation(
            prompt_id="content-only",
            model_id="model-a",
            repetition=1,
            qualification_report=tmp_path / "q1.json",
            run_directory=baseline_run,
        ),
        MatrixObservation(
            prompt_id="structure-aware",
            model_id="model-a",
            repetition=1,
            qualification_report=tmp_path / "q2.json",
            run_directory=context_run,
        ),
    )
    return QualificationMatrixManifest(
        matrix_id="prompt-delta-test",
        corpus_id="roles-v1",
        prompts=prompts,
        models=(ModelCandidate(id="model-a", provider="local"),),
        observations=observations,
    )


def test_prompt_comparison_detects_improvement_and_context_only_resolution(tmp_path: Path) -> None:
    first = _reference("c1", "The system shall be verified.")
    second = _reference("c2", "The system should be validated.")
    local = tmp_path / "local"
    published = tmp_path / "published"
    baseline_run = tmp_path / "content"
    context_run = tmp_path / "context"
    CorpusManifestRepository(local).write(
        EvaluationCorpusManifest(
            corpus_id="roles-v1",
            task="semantic-profile-classification",
            corpus_version="1.0.0",
            selection_strategy="test",
            seed=1,
            clauses=(
                CorpusClause(clause=first, strata={"role": "requirement"}),
                CorpusClause(clause=second, strata={"role": "recommendation"}),
            ),
        )
    )
    gold = _candidate(first, StatementFunction.REQUIREMENT).model_copy(
        update={
            "lifecycle_status": AnnotationLifecycleStatus.PUBLISHED,
            "annotation": StatementFunctionSelection(
                statement_functions=(StatementFunction.REQUIREMENT,),
                primary_function=StatementFunction.REQUIREMENT,
            ),
            "review": AnnotationReview(
                decision=ReviewDecision.CORRECTED,
                reviewer="reviewer",
                reviewed_at=datetime(2026, 8, 30, tzinfo=UTC),
            ),
        }
    )
    ClauseAnnotationRepository(published).write("roles-v1", gold)

    _write_prediction(baseline_run, _candidate(first, StatementFunction.RECOMMENDATION))
    _write_prediction(context_run, _candidate(first, StatementFunction.REQUIREMENT))
    _write_prediction(context_run, _candidate(second, StatementFunction.RECOMMENDATION))

    report = build_prompt_comparison_report(
        manifest=_manifest(tmp_path, baseline_run, context_run),
        local_corpus_root=local,
        published_corpus_root=published,
    )

    assert len(report.comparisons) == 1
    comparison = report.comparisons[0]
    assert comparison.comparable_clauses == 2
    assert comparison.outcome_counts == {
        "improved": 1,
        "resolved_only_by_context": 1,
    }
    first_case = next(case for case in comparison.cases if case.clause_key.endswith(":c1"))
    assert first_case.evidence_source == "published"
    assert first_case.candidate_score > first_case.baseline_score

    json_path, markdown_path = persist_prompt_comparison_report(report, tmp_path / "out")
    assert json_path.exists()
    assert "content-only → structure-aware" in markdown_path.read_text(encoding="utf-8")


def test_prompt_comparison_does_not_claim_improvement_without_evidence(tmp_path: Path) -> None:
    reference = _reference("c1", "Informative prose.")
    local = tmp_path / "local"
    baseline_run = tmp_path / "content"
    context_run = tmp_path / "context"
    CorpusManifestRepository(local).write(
        EvaluationCorpusManifest(
            corpus_id="roles-v1",
            task="semantic-profile-classification",
            corpus_version="1.0.0",
            selection_strategy="test",
            seed=1,
            clauses=(CorpusClause(clause=reference, strata={}),),
        )
    )
    _write_prediction(baseline_run, _candidate(reference, StatementFunction.DESCRIPTION))
    _write_prediction(context_run, _candidate(reference, StatementFunction.EXPLANATION))

    report = build_prompt_comparison_report(
        manifest=_manifest(tmp_path, baseline_run, context_run),
        local_corpus_root=local,
        published_corpus_root=tmp_path / "published",
    )

    assert report.comparisons[0].outcome_counts == {"changed": 1}
    assert report.comparisons[0].cases[0].evidence_source is None
