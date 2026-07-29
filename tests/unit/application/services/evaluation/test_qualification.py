from datetime import UTC, datetime
from pathlib import Path

import yaml

from standards_atlas.application.services.evaluation import (
    AnnotationGenerator,
    AnnotationLifecycleStatus,
    AnnotationQualificationService,
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
from standards_atlas.domain.model import StatementFunction


def _reference(clause_id: str, text: str) -> ClauseReference:
    return ClauseReference(
        knowledge_domain="functional-safety",
        document_key="IEC61508-3",
        clause_id=clause_id,
        content_hash=normalized_content_hash(text),
    )


def _candidate(
    reference: ClauseReference,
    role: StatementFunction,
    confidence: float = 0.8,
) -> ClauseEvaluationAnnotation:
    return ClauseEvaluationAnnotation(
        task="statement-function-classification",
        lifecycle_status=AnnotationLifecycleStatus.PROPOSED,
        clause=reference,
        proposal=StatementFunctionSelection(
            statement_functions=(role,), primary_function=role, confidence=confidence
        ),
        generator=AnnotationGenerator(
            provider="local",
            model="model-a",
            prompt_id="p1",
            generated_at=datetime(2026, 7, 28, tzinfo=UTC),
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


def test_qualification_resolves_gold_silver_structure_and_slices(tmp_path: Path) -> None:
    first = _reference("c1", "The system shall be verified.")
    second = _reference("c2", "The system should be validated.")
    corpus_id = "roles-v1"
    local = tmp_path / "local"
    published = tmp_path / "data"
    run = tmp_path / "run-a"
    manifest = EvaluationCorpusManifest(
        corpus_id=corpus_id,
        task="statement-function-classification",
        corpus_version="1.0.0",
        selection_strategy="representative_stratified",
        seed=42,
        clauses=(
            CorpusClause(
                clause=first,
                strata={"role": "requirement", "document_type": "standard"},
            ),
            CorpusClause(
                clause=second,
                strata={"role": "recommendation", "document_type": "standard"},
            ),
        ),
    )
    CorpusManifestRepository(local).write(manifest)
    reviewed = _candidate(first, StatementFunction.REQUIREMENT).model_copy(
        update={
            "lifecycle_status": AnnotationLifecycleStatus.PUBLISHED,
            "annotation": StatementFunctionSelection(
                statement_functions=(StatementFunction.REQUIREMENT,),
                primary_function=StatementFunction.REQUIREMENT,
            ),
            "review": AnnotationReview(
                decision=ReviewDecision.ACCEPTED,
                reviewer="reviewer",
                reviewed_at=datetime(2026, 7, 28, tzinfo=UTC),
            ),
        }
    )
    ClauseAnnotationRepository(published).write(corpus_id, reviewed)
    _write_prediction(run, _candidate(first, StatementFunction.REQUIREMENT, 0.9))
    _write_prediction(run, _candidate(second, StatementFunction.REQUIREMENT, 0.6))

    report, json_path, markdown_path = AnnotationQualificationService().evaluate(
        corpus_id=corpus_id,
        run_directory=run,
        local_corpus_root=local,
        published_corpus_root=published,
        output_directory=tmp_path / "reports",
    )

    assert report.coverage.corpus_clauses == 2
    assert report.coverage.predictions == 2
    assert report.coverage.published_gold == 1
    assert report.gold_agreement.evaluated == 1
    assert report.gold_agreement.micro_f1 == 1.0
    assert report.silver_agreement.evaluated == 2
    assert report.structure_agreement.evaluated == 2
    assert report.structure_agreement.micro_f1 == 0.5
    assert report.calibration.covered == 1
    assert any(item.dimension == "knowledge_domain" for item in report.slices)
    assert any(item.dimension == "document_type" for item in report.slices)
    assert json_path.exists()
    assert "Primary-role confusion" in markdown_path.read_text(encoding="utf-8")


def test_published_gold_shadows_local_proposal_for_silver(tmp_path: Path) -> None:
    reference = _reference("c1", "A requirement.")
    corpus_id = "roles-v1"
    local = tmp_path / "local"
    published = tmp_path / "data"
    run = tmp_path / "run"
    CorpusManifestRepository(local).write(
        EvaluationCorpusManifest(
            corpus_id=corpus_id,
            task="statement-function-classification",
            corpus_version="1",
            selection_strategy="random",
            seed=1,
            clauses=(CorpusClause(clause=reference, strata={"role": "recommendation"}),),
        )
    )
    ClauseAnnotationRepository(local).write(
        corpus_id,
        _candidate(reference, StatementFunction.RECOMMENDATION),
    )
    gold = _candidate(reference, StatementFunction.REQUIREMENT).model_copy(
        update={
            "lifecycle_status": AnnotationLifecycleStatus.PUBLISHED,
            "annotation": StatementFunctionSelection(
                statement_functions=(StatementFunction.REQUIREMENT,),
                primary_function=StatementFunction.REQUIREMENT,
            ),
            "review": AnnotationReview(
                decision=ReviewDecision.CORRECTED,
                reviewer="r",
                reviewed_at=datetime(2026, 7, 28, tzinfo=UTC),
            ),
        }
    )
    ClauseAnnotationRepository(published).write(corpus_id, gold)
    _write_prediction(run, _candidate(reference, StatementFunction.REQUIREMENT))

    report, _, _ = AnnotationQualificationService().evaluate(
        corpus_id=corpus_id,
        run_directory=run,
        local_corpus_root=local,
        published_corpus_root=published,
        output_directory=tmp_path / "out",
    )

    assert report.gold_agreement.micro_f1 == 1.0
    assert report.silver_agreement.micro_f1 == 1.0
    assert report.coverage.published_gold == 1
    assert report.coverage.local_proposals == 0
