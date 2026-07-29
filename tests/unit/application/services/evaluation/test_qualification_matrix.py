from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from standards_atlas.application.services.evaluation import (
    AgreementMetrics,
    AnnotationQualificationReport,
    CalibrationMetrics,
    CorpusCoverage,
    ModelPromptQualificationService,
    PromptCandidate,
    QualificationMatrixManifest,
    resolve_prompt_version,
)


def _agreement(f1: float, coverage: float = 1.0) -> AgreementMetrics:
    return AgreementMetrics(
        eligible=10,
        evaluated=round(10 * coverage),
        coverage=coverage,
        exact_match_rate=f1,
        primary_function_accuracy=f1,
        micro_precision=f1,
        micro_recall=f1,
        micro_f1=f1,
        macro_f1=f1,
    )


def _write_report(path: Path, f1: float, corpus_id: str = "roles-v1") -> None:
    report = AnnotationQualificationReport(
        corpus_id=corpus_id,
        generated_at=datetime(2026, 7, 28, tzinfo=UTC),
        prediction_source="run",
        coverage=CorpusCoverage(
            corpus_clauses=10,
            predictions=10,
            published_gold=10,
            local_reviewed_gold=0,
            local_proposals=0,
            structure_labels=10,
            stale_or_invalid=0,
            missing_predictions=0,
        ),
        gold_agreement=_agreement(f1),
        silver_agreement=_agreement(f1),
        structure_agreement=_agreement(f1),
        calibration=CalibrationMetrics(covered=10, coverage=1.0),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _manifest(tmp_path: Path) -> Path:
    observations = []
    for prompt_index in range(1, 5):
        for model_id in ("fast", "accurate"):
            for repetition in (1, 2):
                report = tmp_path / "reports" / f"p{prompt_index}-{model_id}-{repetition}.json"
                f1 = 0.90 if model_id == "accurate" else 0.80
                _write_report(report, f1)
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
        "matrix_id": "semantic-role-v1",
        "corpus_id": "roles-v1",
        "repetitions": 2,
        "prompts": [{"id": f"p{index}"} for index in range(1, 5)],
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


def test_matrix_aggregates_repetitions_and_builds_pareto_front(tmp_path: Path) -> None:
    manifest = QualificationMatrixManifest.load(_manifest(tmp_path))
    report, json_path, markdown_path = ModelPromptQualificationService().evaluate(
        manifest, tmp_path / "output"
    )

    assert report.passed
    assert len(report.candidates) == 8
    assert " / accurate / " in report.ranking[0]
    assert any(" / fast / " in key for key in report.pareto_front)
    assert any(" / accurate / " in key for key in report.pareto_front)
    assert json_path.exists()
    assert "Regression diagnostics" in markdown_path.read_text(encoding="utf-8")


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
    assert not report.passed


def test_baseline_drop_threshold_detects_regression(tmp_path: Path) -> None:
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


def test_manifest_requires_exactly_four_prompts(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["prompts"] = payload["prompts"][:3]
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly four"):
        QualificationMatrixManifest.load(path)


def test_optional_reasoning_mode_does_not_require_observations(tmp_path: Path) -> None:
    payload = yaml.safe_load(_manifest(tmp_path).read_text(encoding="utf-8"))
    payload["reasoning_modes"] = [
        {"id": "disabled", "enabled": False, "optional": False},
        {"id": "enabled", "enabled": True, "optional": True},
    ]
    path = tmp_path / "reasoning-matrix.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    report, _, _ = ModelPromptQualificationService().evaluate(
        QualificationMatrixManifest.load(path), tmp_path / "reasoning-output"
    )

    assert report.passed
    optional = [item for item in report.candidates if item.reasoning_mode_id == "enabled"]
    assert len(optional) == 8
    assert all(item.reasoning_optional for item in optional)
    assert all(not item.regressions for item in optional)


def test_reasoning_mode_is_part_of_observation_identity(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["reasoning_modes"] = [
        {"id": "disabled", "enabled": False},
        {"id": "enabled", "enabled": True, "optional": True},
    ]
    enabled = dict(payload["observations"][0])
    enabled["reasoning_mode_id"] = "enabled"
    payload["observations"].append(enabled)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    manifest = QualificationMatrixManifest.load(path)

    assert len(manifest.observations) == 17


def test_prompt_aliases_resolve_to_installed_resources() -> None:
    resources = Path("src/standards_atlas/resources/semantic")

    assert (
        resolve_prompt_version(PromptCandidate(id="content-only"), resources=resources)
        == "content-only-v1"
    )
    assert (
        resolve_prompt_version(PromptCandidate(id="reference-aware"), resources=resources)
        == "evidence-first-v1"
    )
    assert (
        resolve_prompt_version(PromptCandidate(id="deliberative"), resources=resources)
        == "bounded-reasoning-v1"
    )


def test_model_repetitions_override_global_default(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["repetitions"] = 3
    payload["models"][0]["repetitions"] = 1
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    manifest = QualificationMatrixManifest.load(path)

    assert manifest.repetitions_for(manifest.models[0]) == 1
    assert manifest.repetitions_for(manifest.models[1]) == 3


def test_model_repetitions_must_be_positive(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["models"][0]["repetitions"] = 0
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="greater than or equal to 1"):
        QualificationMatrixManifest.load(path)
