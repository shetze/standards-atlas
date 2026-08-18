import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from standards_atlas.application.semantic_qualification.qualification import (
    AgreementMetrics,
    AnnotationQualificationReport,
    CalibrationMetrics,
    CorpusCoverage,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    PromptCandidate,
    QualificationMatrixManifest,
    resolve_prompt_version,
)
from standards_atlas.application.services.evaluation import ModelPromptQualificationService


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


def test_model_repetitions_zero_disables_model(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["models"][0]["repetitions"] = 0
    payload["observations"] = [
        item for item in payload["observations"] if item["model_id"] != "fast"
    ]
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    manifest = QualificationMatrixManifest.load(path)
    report, _, _ = ModelPromptQualificationService().evaluate(
        manifest, tmp_path / "disabled-model-output"
    )

    assert manifest.repetitions_for(manifest.models[0]) == 0
    assert report.passed
    assert len(report.candidates) == 4
    assert all(candidate.model_id == "accurate" for candidate in report.candidates)
    assert not any("fast" in diagnostic for diagnostic in report.diagnostics)


def test_disabled_model_rejects_existing_observations(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["models"][0]["repetitions"] = 0
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="configured repetitions 0 for fast"):
        QualificationMatrixManifest.load(path)


def test_optional_unexecuted_candidate_is_not_ranked_or_passed(tmp_path: Path) -> None:
    payload = yaml.safe_load(_manifest(tmp_path).read_text(encoding="utf-8"))
    payload["reasoning_modes"] = [
        {"id": "disabled", "enabled": False},
        {"id": "enabled", "enabled": True, "optional": True},
    ]
    path = tmp_path / "optional.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    report, _, markdown = ModelPromptQualificationService().evaluate(
        QualificationMatrixManifest.load(path), tmp_path / "optional-output"
    )

    optional = [item for item in report.candidates if item.reasoning_mode_id == "enabled"]
    assert all(item.status == "unsupported" for item in optional)
    assert all(not item.passed for item in optional)
    assert all(not item.qualification_eligible for item in optional)
    assert not any(" / enabled" in key for key in report.ranking)
    assert "## Not ranked" in markdown.read_text(encoding="utf-8")


def test_missing_gold_is_reported_as_unavailable_not_zero(tmp_path: Path) -> None:
    manifest = QualificationMatrixManifest.load(_manifest(tmp_path))
    for observation in manifest.observations:
        payload = yaml.safe_load(observation.qualification_report.read_text(encoding="utf-8"))
        payload["gold_agreement"]["eligible"] = 0
        payload["gold_agreement"]["evaluated"] = 0
        payload["gold_agreement"]["coverage"] = 0.0
        observation.qualification_report.write_text(json.dumps(payload), encoding="utf-8")

    report, _, markdown = ModelPromptQualificationService().evaluate(
        manifest, tmp_path / "no-gold-output"
    )

    assert all(item.mean_gold_f1 is None for item in report.candidates)
    assert all(item.mean_gold_coverage is None for item in report.candidates)
    assert "n/a" in markdown.read_text(encoding="utf-8")


def test_model_generation_configuration_is_nested_and_validated(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["models"][0]["generation"] = {
        "max_output_tokens": 512,
        "adaptive_question_max_tokens": 384,
        "truncation_retry_max_tokens": 768,
        "reasoning_mode": "disabled",
        "retry_on_truncation": True,
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    manifest = QualificationMatrixManifest.load(path)
    generation = manifest.models[0].generation

    assert generation.max_output_tokens == 512
    assert generation.adaptive_question_max_tokens == 384
    assert generation.truncation_retry_max_tokens == 768
    assert generation.reasoning_mode == "disabled"
    assert generation.retry_on_truncation


def test_cascade_manifest_validates_stages(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["execution"] = {
        "mode": "cascade",
        "stages": [
            {"id": "efficient", "models": ["fast"], "apply_to": "all"},
            {"id": "escalation", "models": ["accurate"], "apply_to": "unresolved"},
        ],
        "resolution": {
            "minimum_successful_models": 1,
            "accepted_categories": ["unanimous", "strong_consensus"],
            "minimum_confidence": 0.8,
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    manifest = QualificationMatrixManifest.load(path)

    assert manifest.execution.mode == "cascade"
    assert manifest.execution.stages[1].apply_to == "unresolved"
    assert manifest.execution.resolution.minimum_confidence == 0.8


def test_cascade_rejects_unknown_models(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["execution"] = {
        "mode": "cascade",
        "stages": [
            {"id": "efficient", "models": ["missing"], "apply_to": "all"},
            {"id": "escalation", "models": ["accurate"], "apply_to": "unresolved"},
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown models"):
        QualificationMatrixManifest.load(path)


def test_cascade_stage_can_select_prompts(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["execution"] = {
        "mode": "cascade",
        "stages": [
            {
                "id": "efficient",
                "models": ["fast"],
                "prompts": ["p1", "p2"],
                "apply_to": "all",
            },
            {
                "id": "escalation",
                "models": ["accurate"],
                "prompts": ["p3", "p4"],
                "apply_to": "unresolved",
            },
        ],
    }
    payload["observations"] = [
        item
        for item in payload["observations"]
        if (item["model_id"] == "fast" and item["prompt_id"] in {"p1", "p2"})
        or (item["model_id"] == "accurate" and item["prompt_id"] in {"p3", "p4"})
    ]
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    manifest = QualificationMatrixManifest.load(path)
    report, _, _ = ModelPromptQualificationService().evaluate(
        manifest, tmp_path / "stage-prompts-output"
    )

    assert [prompt.id for prompt in manifest.prompts_for_model("fast")] == ["p1", "p2"]
    assert [prompt.id for prompt in manifest.prompts_for_model("accurate")] == ["p3", "p4"]
    assert len(report.candidates) == 4
    assert not any("missing all runs" in item for item in report.diagnostics)


def test_cascade_stage_without_prompt_selection_uses_all_prompts(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["execution"] = {
        "mode": "cascade",
        "stages": [
            {"id": "efficient", "models": ["fast"], "apply_to": "all"},
            {
                "id": "escalation",
                "models": ["accurate"],
                "apply_to": "unresolved",
            },
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    manifest = QualificationMatrixManifest.load(path)

    assert manifest.prompts_for_model("fast") == manifest.prompts
    assert manifest.prompts_for_model("accurate") == manifest.prompts


def test_cascade_rejects_unknown_stage_prompts(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["execution"] = {
        "mode": "cascade",
        "stages": [
            {
                "id": "efficient",
                "models": ["fast"],
                "prompts": ["missing"],
                "apply_to": "all",
            },
            {
                "id": "escalation",
                "models": ["accurate"],
                "apply_to": "unresolved",
            },
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown prompts"):
        QualificationMatrixManifest.load(path)


def test_cascade_resolution_escalates_dimension_disagreement() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeResolutionConfig,
        cascade_escalation_reasons,
    )

    resolution = CascadeResolutionConfig(
        minimum_successful_models=3,
        minimum_confidence=0.6,
        escalate_on_applicability_disagreement=True,
        escalate_on_responsibility_disagreement=True,
    )
    clause = SimpleNamespace(
        participating_models=3,
        category=SimpleNamespace(value="strong_consensus"),
        statement_function_confidence=1.0,
        applicability_unanimous=False,
        responsibility_unanimous=False,
    )

    assert cascade_escalation_reasons(clause, resolution) == (
        "applicability_disagreement",
        "responsibility_disagreement",
    )


def test_cascade_resolution_accepts_unanimous_secondary_dimensions() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeResolutionConfig,
        cascade_escalation_reasons,
    )

    clause = SimpleNamespace(
        participating_models=3,
        category=SimpleNamespace(value="majority_consensus"),
        statement_function_confidence=2 / 3,
        applicability_unanimous=True,
        responsibility_unanimous=True,
    )

    assert cascade_escalation_reasons(clause, CascadeResolutionConfig()) == ()


def test_cascade_stage_can_override_resolution_policy() -> None:
    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeStage,
    )

    stage = CascadeStage.model_validate(
        {
            "id": "intermediate",
            "models": ["fast-a", "fast-b"],
            "apply_to": "unresolved",
            "resolution": {
                "minimum_successful_models": 5,
                "escalate_on_applicability_disagreement": False,
                "escalate_on_responsibility_disagreement": False,
                "minimum_applicability_confidence": 0.75,
                "minimum_responsibility_confidence": 0.80,
            },
        }
    )

    assert stage.resolution is not None
    assert stage.resolution.minimum_successful_models == 5
    assert stage.resolution.minimum_applicability_confidence == 0.75
    assert stage.resolution.minimum_responsibility_confidence == 0.80


def test_cascade_resolution_uses_dimension_confidence_after_intermediate_stage() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeResolutionConfig,
        cascade_escalation_reasons,
    )

    resolution = CascadeResolutionConfig(
        minimum_successful_models=5,
        minimum_confidence=0.6,
        escalate_on_applicability_disagreement=False,
        escalate_on_responsibility_disagreement=False,
        minimum_applicability_confidence=0.75,
        minimum_responsibility_confidence=0.80,
    )
    resolved = SimpleNamespace(
        participating_models=7,
        category=SimpleNamespace(value="strong_consensus"),
        statement_function_confidence=6 / 7,
        applicability_unanimous=False,
        responsibility_unanimous=False,
        applicability_present=True,
        applicability_confidence=6 / 7,
        applicability_support={"present": 6 / 7, "exception": 6 / 7},
        responsibility_present=True,
        responsibility_confidence=6 / 7,
        responsibility_support={
            "present": 6 / 7,
            "responsibility_assignment": 6 / 7,
        },
    )
    unresolved = SimpleNamespace(
        **{
            **resolved.__dict__,
            "applicability_confidence": 5 / 7,
            "applicability_support": {"present": 5 / 7, "exception": 5 / 7},
        }
    )

    assert cascade_escalation_reasons(resolved, resolution) == ()
    assert cascade_escalation_reasons(unresolved, resolution) == ("applicability_confidence",)


def test_cascade_resolution_can_accept_confident_absence() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeResolutionConfig,
        cascade_escalation_reasons,
    )

    resolution = CascadeResolutionConfig(
        minimum_successful_models=5,
        escalate_on_applicability_disagreement=False,
        escalate_on_responsibility_disagreement=False,
        minimum_applicability_confidence=0.75,
        minimum_responsibility_confidence=0.80,
    )
    clause = SimpleNamespace(
        participating_models=7,
        category=SimpleNamespace(value="strong_consensus"),
        statement_function_confidence=6 / 7,
        applicability_unanimous=False,
        responsibility_unanimous=False,
        applicability_present=False,
        applicability_confidence=0.0,
        applicability_support={"present": 1 / 7},
        responsibility_present=False,
        responsibility_confidence=0.0,
        responsibility_support={"present": 1 / 7},
    )

    assert cascade_escalation_reasons(clause, resolution) == ()


def test_cascade_unresolved_clause_ids_are_monotonic_per_stage() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeResolutionConfig,
        cascade_unresolved_clause_ids,
    )

    resolution = CascadeResolutionConfig(minimum_successful_models=5)
    resolved_before_stage = SimpleNamespace(
        clause_id="resolved-before-stage",
        participating_models=3,
        category=SimpleNamespace(value="strong_consensus"),
        statement_function_confidence=1.0,
        applicability_unanimous=True,
        responsibility_unanimous=True,
    )
    resolved_in_stage = SimpleNamespace(
        clause_id="resolved-in-stage",
        participating_models=7,
        category=SimpleNamespace(value="strong_consensus"),
        statement_function_confidence=1.0,
        applicability_unanimous=True,
        responsibility_unanimous=True,
    )
    unresolved_in_stage = SimpleNamespace(
        clause_id="unresolved-in-stage",
        participating_models=7,
        category=SimpleNamespace(value="disputed"),
        statement_function_confidence=0.4,
        applicability_unanimous=True,
        responsibility_unanimous=True,
    )

    unresolved, reasons = cascade_unresolved_clause_ids(
        [resolved_before_stage, resolved_in_stage, unresolved_in_stage],
        stage_clause_ids=("resolved-in-stage", "unresolved-in-stage"),
        resolution=resolution,
    )

    assert unresolved == ("unresolved-in-stage",)
    assert set(reasons) == {"resolved-in-stage", "unresolved-in-stage"}
    assert "resolved-before-stage" not in reasons


def test_stage_resolver_accepts_three_of_four_statement_votes() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeResolutionConfig,
        cascade_stage_escalation_reasons,
    )

    resolution = CascadeResolutionConfig(
        minimum_successful_models=5,
        statement_function_resolution_mode="stage_resolver",
        statement_function_resolver_min_confidence=0.75,
        minimum_applicability_confidence=0.75,
        minimum_responsibility_confidence=0.80,
    )
    cumulative = SimpleNamespace(
        participating_models=7,
        category=SimpleNamespace(value="disputed"),
        statement_function_confidence=4 / 7,
        applicability_present=False,
        applicability_confidence=0.0,
        applicability_support={"present": 0.0},
        applicability_unanimous=True,
        responsibility_present=False,
        responsibility_confidence=0.0,
        responsibility_support={"present": 0.0},
        responsibility_unanimous=True,
    )
    stage = SimpleNamespace(statement_function_confidence=3 / 4)

    assert (
        cascade_stage_escalation_reasons(
            cumulative_clause=cumulative,
            stage_clause=stage,
            previous_reasons=("statement_function_confidence",),
            resolution=resolution,
        )
        == ()
    )


def test_stage_resolution_does_not_reopen_resolved_statement_function() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeResolutionConfig,
        cascade_stage_escalation_reasons,
    )

    resolution = CascadeResolutionConfig(
        minimum_successful_models=5,
        statement_function_resolution_mode="stage_resolver",
        statement_function_resolver_min_confidence=0.75,
        minimum_applicability_confidence=0.75,
        minimum_responsibility_confidence=0.80,
    )
    cumulative = SimpleNamespace(
        participating_models=7,
        category=SimpleNamespace(value="disputed"),
        statement_function_confidence=3 / 7,
        applicability_present=True,
        applicability_confidence=6 / 7,
        applicability_support={"present": 6 / 7, "exception": 6 / 7},
        applicability_unanimous=False,
        responsibility_present=False,
        responsibility_confidence=0.0,
        responsibility_support={"present": 0.0},
        responsibility_unanimous=True,
    )
    stage = SimpleNamespace(statement_function_confidence=0.25)

    assert (
        cascade_stage_escalation_reasons(
            cumulative_clause=cumulative,
            stage_clause=stage,
            previous_reasons=("applicability_disagreement",),
            resolution=resolution,
        )
        == ()
    )


def test_stage_resolution_uses_cumulative_applicability_confidence() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeResolutionConfig,
        cascade_stage_escalation_reasons,
    )

    resolution = CascadeResolutionConfig(
        minimum_successful_models=5,
        statement_function_resolution_mode="stage_resolver",
        minimum_applicability_confidence=0.75,
        minimum_responsibility_confidence=0.80,
    )
    cumulative = SimpleNamespace(
        participating_models=7,
        category=SimpleNamespace(value="strong_consensus"),
        statement_function_confidence=1.0,
        applicability_present=True,
        applicability_confidence=5 / 7,
        applicability_support={"present": 5 / 7, "exception": 5 / 7},
        applicability_unanimous=False,
        responsibility_present=False,
        responsibility_confidence=0.0,
        responsibility_support={"present": 0.0},
        responsibility_unanimous=True,
    )
    stage = SimpleNamespace(statement_function_confidence=1.0)

    assert cascade_stage_escalation_reasons(
        cumulative_clause=cumulative,
        stage_clause=stage,
        previous_reasons=("applicability_disagreement",),
        resolution=resolution,
    ) == ("applicability_confidence",)


def test_capture_resolved_dimensions_persists_stage_resolver_statement() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        capture_resolved_dimensions,
    )

    cumulative = SimpleNamespace(
        primary_knowledge_kind=None,
        knowledge_kind_confidence=1.0,
        knowledge_kind_category=SimpleNamespace(value="unanimous"),
        applicability_present=False,
        proposed_applicability_functions=(),
        applicability_decision_confidence=1.0,
        applicability_category=SimpleNamespace(value="unanimous"),
        responsibility_present=False,
        proposed_responsibility_functions=(),
        responsibility_decision_confidence=1.0,
        responsibility_category=SimpleNamespace(value="unanimous"),
    )
    resolver = SimpleNamespace(
        primary_function=SimpleNamespace(value="description"),
        statement_function_confidence=1.0,
        statement_function_category=SimpleNamespace(value="unanimous"),
    )

    captured = capture_resolved_dimensions(
        cumulative_clause=cumulative,
        stage_clause=resolver,
        previous_reasons=("statement_function_confidence",),
        remaining_reasons=(),
        source="resolver-stage",
    )

    assert captured == {
        "statement_function": {
            "value": "description",
            "confidence": 1.0,
            "category": "unanimous",
            "source": "resolver-stage",
        }
    }


def test_cascade_escalates_applicability_structural_conflict() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeResolutionConfig,
        cascade_escalation_reasons,
    )

    clause = SimpleNamespace(
        participating_models=3,
        category=SimpleNamespace(value="unanimous"),
        statement_function_confidence=1.0,
        applicability_unanimous=True,
        applicability_structural_conflict=True,
        applicability_present=True,
        applicability_confidence=1.0,
        applicability_support={"present": 1.0, "exclusion": 1.0},
        responsibility_unanimous=True,
        responsibility_present=False,
        responsibility_confidence=0.0,
        responsibility_support={"present": 0.0},
    )

    reasons = cascade_escalation_reasons(clause, CascadeResolutionConfig())

    assert "applicability_structural_conflict" in reasons


def test_capture_initial_knowledge_kind_uses_decision_confidence_for_none() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        capture_resolved_dimensions,
    )

    clause = SimpleNamespace(
        primary_function=None,
        statement_function_confidence=1.0,
        statement_function_category=SimpleNamespace(value="unanimous"),
        primary_knowledge_kind=None,
        knowledge_kind_confidence=0.0,
        knowledge_kind_decision_confidence=1.0,
        knowledge_kind_category=SimpleNamespace(value="unanimous"),
        applicability_present=False,
        proposed_applicability_functions=(),
        applicability_decision_confidence=1.0,
        applicability_category=SimpleNamespace(value="unanimous"),
        applicability_structural_conflict=False,
        responsibility_present=False,
        proposed_responsibility_functions=(),
        responsibility_decision_confidence=1.0,
        responsibility_category=SimpleNamespace(value="unanimous"),
    )

    captured = capture_resolved_dimensions(
        cumulative_clause=clause,
        stage_clause=clause,
        previous_reasons=(),
        remaining_reasons=(),
        source="efficient-local",
        initial_stage=True,
    )

    assert captured["knowledge_kind"] == {
        "value": None,
        "confidence": 1.0,
        "category": "unanimous",
        "source": "efficient-local",
    }


def test_effective_cascade_resolution_honors_review_majority_threshold() -> None:
    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeResolutionConfig,
        effective_cascade_resolution,
    )

    configured = CascadeResolutionConfig(minimum_confidence=0.60)
    effective = effective_cascade_resolution(
        configured,
        review_majority_min_confidence=0.67,
    )

    assert configured.minimum_confidence == 0.60
    assert effective.minimum_confidence == 0.67


def test_stage_keeps_unresolved_structural_conflict_without_other_applicability_reason() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CascadeResolutionConfig,
        cascade_stage_escalation_reasons,
    )

    cumulative = SimpleNamespace(
        participating_models=7,
        category=SimpleNamespace(value="unanimous"),
        statement_function_confidence=1.0,
        applicability_structural_conflict=True,
        applicability_present=True,
        applicability_confidence=1.0,
        applicability_support={"present": 1.0, "exclusion": 1.0},
        applicability_unanimous=True,
        responsibility_present=False,
        responsibility_confidence=0.0,
        responsibility_support={"present": 0.0},
        responsibility_unanimous=True,
    )
    stage = SimpleNamespace(statement_function_confidence=1.0)

    reasons = cascade_stage_escalation_reasons(
        cumulative_clause=cumulative,
        stage_clause=stage,
        previous_reasons=("applicability_structural_conflict",),
        resolution=CascadeResolutionConfig(
            escalate_on_applicability_disagreement=False,
            minimum_applicability_confidence=0.75,
        ),
    )

    assert reasons == ("applicability_structural_conflict",)


def test_cached_or_reused_wall_time_does_not_satisfy_duration_threshold(tmp_path: Path) -> None:
    manifest = QualificationMatrixManifest.load(_manifest(tmp_path))
    observations = tuple(
        item.model_copy(
            update={
                "performance_measurement_source": "not_measured",
                "fresh_prediction_count": 0,
                "reused_prediction_count": 10,
                "mean_duration_seconds": 0.5,
            }
        )
        if item.model_id == "fast"
        else item
        for item in manifest.observations
    )
    thresholds = manifest.thresholds.model_copy(update={"max_mean_duration_seconds": 5.0})
    report, _, _ = ModelPromptQualificationService().evaluate(
        manifest.model_copy(update={"observations": observations, "thresholds": thresholds}),
        tmp_path / "output",
    )

    candidate = next(
        item for item in report.candidates if item.prompt_id == "p1" and item.model_id == "fast"
    )
    assert candidate.mean_duration_seconds is None
    assert candidate.performance_measurement_source == "not_measured"
    assert not candidate.passed
    assert "fresh inference performance not measured" in candidate.regressions
