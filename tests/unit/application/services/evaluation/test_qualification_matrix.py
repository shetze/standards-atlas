from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from standards_atlas.application.semantic_qualification.applicability_qualification import (
    ApplicabilityAgreementMetrics,
    ApplicabilityQualificationReport,
    CalibrationMetrics,
    CorpusCoverage,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    CascadeResolutionConfig,
    PromptCandidate,
    QualificationMatrixManifest,
    capture_resolved_dimensions,
    cascade_escalation_reasons,
    cascade_stage_escalation_reasons,
    resolve_prompt_version,
)
from standards_atlas.application.services.evaluation import ModelPromptQualificationService


def _agreement(f1: float, coverage: float = 1.0) -> ApplicabilityAgreementMetrics:
    evaluated = round(10 * coverage)
    return ApplicabilityAgreementMetrics(
        eligible=10,
        evaluated=evaluated,
        coverage=coverage,
        accuracy=f1,
        precision=f1,
        recall=f1,
        specificity=f1,
        f1=f1,
        true_positive=evaluated,
        false_positive=0,
        true_negative=0,
        false_negative=0,
    )


def _write_report(path: Path, f1: float, corpus_id: str = "applicability-v1") -> None:
    report = ApplicabilityQualificationReport(
        corpus_id=corpus_id,
        generated_at=datetime(2026, 9, 15, tzinfo=UTC),
        prediction_source="run",
        coverage=CorpusCoverage(
            corpus_clauses=10,
            predictions=10,
            published_gold=10,
            local_reviewed_gold=0,
            local_proposals=0,
            stale_or_invalid=0,
            missing_predictions=0,
        ),
        gold_agreement=_agreement(f1),
        calibration=CalibrationMetrics(covered=10, coverage=1.0),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _manifest(tmp_path: Path) -> Path:
    observations = []
    for prompt_index in range(1, 3):
        for model_id in ("fast", "accurate"):
            for repetition in (1, 2):
                report = tmp_path / "reports" / f"p{prompt_index}-{model_id}-{repetition}.json"
                _write_report(report, 0.90 if model_id == "accurate" else 0.80)
                observations.append(
                    {
                        "prompt_id": f"p{prompt_index}",
                        "model_id": model_id,
                        "repetition": repetition,
                        "qualification_report": str(report.relative_to(tmp_path)),
                        "mean_duration_seconds": 4.0 if model_id == "fast" else 10.0,
                        "peak_memory_gb": 4.0 if model_id == "fast" else 8.0,
                    }
                )
    payload = {
        "schema_version": 1,
        "matrix_id": "applicability-presence-v1",
        "corpus_id": "applicability-v1",
        "repetitions": 2,
        "prompts": [{"id": "p1"}, {"id": "p2"}],
        "models": [
            {"id": "fast", "provider": "local", "declared_memory_gb": 4.0},
            {"id": "accurate", "provider": "local", "declared_memory_gb": 8.0},
        ],
        "observations": observations,
        "thresholds": {
            "min_gold_f1": 0.75,
            "min_gold_coverage": 0.9,
            "max_gold_f1_stddev": 0.02,
        },
    }
    path = tmp_path / "matrix.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_matrix_aggregates_applicability_repetitions_and_builds_pareto_front(
    tmp_path: Path,
) -> None:
    manifest = QualificationMatrixManifest.load(_manifest(tmp_path))
    report, json_path, markdown_path = ModelPromptQualificationService().evaluate(
        manifest, tmp_path / "output"
    )

    assert report.passed
    assert len(report.candidates) == 4
    assert " / accurate / " in report.ranking[0]
    assert any(" / fast / " in key for key in report.pareto_front)
    assert any(" / accurate / " in key for key in report.pareto_front)
    assert json_path.exists()
    assert markdown_path.exists()


def test_missing_repetition_fails_candidate(tmp_path: Path) -> None:
    manifest = QualificationMatrixManifest.load(_manifest(tmp_path))
    observations = tuple(
        item
        for item in manifest.observations
        if not (item.prompt_id == "p1" and item.model_id == "fast" and item.repetition == 2)
    )
    report, _, _ = ModelPromptQualificationService().evaluate(
        manifest.model_copy(update={"observations": observations}),
        tmp_path / "output",
    )

    candidate = next(
        item for item in report.candidates if item.prompt_id == "p1" and item.model_id == "fast"
    )
    assert not candidate.passed
    assert "completed repetitions" in candidate.regressions[0]


def test_baseline_drop_threshold_detects_applicability_regression(tmp_path: Path) -> None:
    manifest = QualificationMatrixManifest.load(_manifest(tmp_path))
    thresholds = manifest.thresholds.model_copy(
        update={
            "baseline_prompt_id": "p1",
            "baseline_model_id": "accurate",
            "max_gold_f1_drop": 0.05,
        }
    )
    report, _, _ = ModelPromptQualificationService().evaluate(
        manifest.model_copy(update={"thresholds": thresholds}),
        tmp_path / "output",
    )
    fast = next(
        item for item in report.candidates if item.prompt_id == "p1" and item.model_id == "fast"
    )
    assert not fast.passed
    assert any("baseline allowance" in item for item in fast.regressions)


def test_manifest_rejects_non_current_schema_version(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "1.6"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        QualificationMatrixManifest.load(path)


def test_manifest_requires_at_least_one_prompt(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["prompts"] = []
    payload["observations"] = []
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="at least one prompt"):
        QualificationMatrixManifest.load(path)


def test_resolve_prompt_version_only_uses_applicability_task(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    prompt = resources / "prompts" / "applicability-presence" / "app-v1"
    prompt.mkdir(parents=True)
    (prompt / "prompt.json").write_text("{}", encoding="utf-8")
    assert (
        resolve_prompt_version(
            PromptCandidate(id="app-v1"),
            resources=resources,
        )
        == "app-v1"
    )


def _clause(*, confidence: float, unanimous: bool = True, models: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        participating_models=models,
        applicability_participating_models=models,
        applicability_category=SimpleNamespace(
            value="unanimous" if unanimous else "majority_consensus"
        ),
        applicability_presence_confidence=confidence,
        applicability_decision_confidence=confidence,
        applicability_presence_unanimous=unanimous,
        applicability_present=True,
    )


def test_cascade_resolution_is_presence_only() -> None:
    resolution = CascadeResolutionConfig(
        minimum_successful_models=3,
        minimum_presence_confidence=0.75,
        escalate_on_presence_disagreement=False,
    )
    assert cascade_escalation_reasons(_clause(confidence=0.70), resolution) == (
        "applicability_presence_confidence",
    )
    assert cascade_escalation_reasons(_clause(confidence=0.80, unanimous=False), resolution) == ()


def test_stage_resolution_rechecks_only_previous_presence_reason() -> None:
    resolution = CascadeResolutionConfig(minimum_presence_confidence=0.75)
    reasons = cascade_stage_escalation_reasons(
        cumulative_clause=_clause(confidence=0.90),
        stage_clause=_clause(confidence=0.90),
        previous_reasons=("applicability_presence_confidence",),
        resolution=resolution,
    )
    assert reasons == ()


def test_capture_resolved_dimensions_contains_only_applicability() -> None:
    captured = capture_resolved_dimensions(
        cumulative_clause=_clause(confidence=0.90),
        stage_clause=_clause(confidence=0.90),
        previous_reasons=("applicability_presence_confidence",),
        remaining_reasons=(),
        source="intermediate",
    )
    assert set(captured) == {"applicability"}
    assert captured["applicability"]["present"] is True


def test_model_dimension_eligibility_only_accepts_applicability_presence(tmp_path: Path) -> None:
    manifest = QualificationMatrixManifest.load(_manifest(tmp_path))
    assert manifest.eligible_model_ids_for_dimension("applicability_presence") == (
        "fast",
        "accurate",
    )
    with pytest.raises(ValueError, match="unsupported model-eligibility dimension"):
        manifest.eligible_model_ids_for_dimension("statement_function")
