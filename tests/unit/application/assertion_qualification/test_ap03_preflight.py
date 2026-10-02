from __future__ import annotations

import shutil
from pathlib import Path

from standards_atlas.application.assertion_qualification.ap03_preflight import (
    Ap03ArtifactCheck,
    Ap03ArtifactStatus,
    _check_b0,
    _historical_input_state_hash,
    run_ap03_preflight,
)


def _project_root(tmp_path: Path) -> Path:
    (tmp_path / "cfg").mkdir()
    shutil.copyfile("cfg/llm.yaml", tmp_path / "cfg" / "llm.yaml")
    (tmp_path / "manifests").mkdir()
    return tmp_path


def test_preflight_is_model_free_and_reports_missing_private_originals(tmp_path: Path) -> None:
    project = _project_root(tmp_path)

    report = run_ap03_preflight(project)

    assert report.model_execution is False
    assert report.network_access is False
    assert report.golden_or_knowledge_write is False
    assert report.b0.intact is True
    assert report.historical_replay_ready is False
    assert report.b0_experiment_inputs_ready is False
    assert report.release_state == "not_ready_for_release"
    statuses = {item.artifact_id: item.status for item in report.historical_artifacts}
    assert statuses["v8_review_audit"] is Ap03ArtifactStatus.MISSING
    assert statuses["development_golden_suite"] is Ap03ArtifactStatus.MISSING
    assert statuses["v8_qualification_report"] is Ap03ArtifactStatus.MISSING
    summary = next(
        item
        for item in report.historical_artifacts
        if item.artifact_id == "v8_qualification_summary"
    )
    assert summary.required is False
    assert not any("v8_qualification_summary" in gap for gap in report.gaps)
    assert report.declared_models[0].availability_verified is False


def test_preflight_rejects_reconstructed_or_wrong_historical_audit(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    target = (
        project
        / "local/review/assertions/assertion-pilot/0.1.0"
        / "assertion-review-pilot-v8-reviewed-complete.yaml"
    )
    target.parent.mkdir(parents=True)
    shutil.copyfile(
        "tests/fixtures/assertion_qualification/synthetic-reviewed-complete.yaml", target
    )

    report = run_ap03_preflight(project)
    audit = next(
        item for item in report.historical_artifacts if item.artifact_id == "v8_review_audit"
    )

    assert audit.status is Ap03ArtifactStatus.INVALID
    assert audit.issue == "audit SHA-256 differs from frozen AP01 bytes"
    assert report.historical_replay_ready is False


def test_b0_integrity_detects_prompt_change(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    semantic = tmp_path / "semantic"
    shutil.copytree("src/standards_atlas/resources/semantic", semantic)
    system = (
        semantic
        / "prompts/formal-semantic-knowledge-proposal"
        / "ontology-guided-assertions-source-bound-v1/system.txt"
    )
    system.write_text(system.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")

    result = _check_b0(project, semantic_root=semantic)

    assert result.intact is False
    assert any("system.txt fingerprint changed" in issue for issue in result.issues)


def test_historical_input_state_does_not_depend_on_report_bytes() -> None:
    audit = Ap03ArtifactCheck(
        artifact_id="v8_review_audit",
        required_for=("historical_v8_replay",),
        status=Ap03ArtifactStatus.AVAILABLE,
        sha256="a" * 64,
    )
    golden = Ap03ArtifactCheck(
        artifact_id="development_golden_suite",
        required_for=("historical_v8_replay",),
        status=Ap03ArtifactStatus.AVAILABLE,
        sha256="b" * 64,
        model_sha256="c" * 64,
    )
    report_a = Ap03ArtifactCheck(
        artifact_id="v8_qualification_report",
        required_for=("historical_comparison",),
        status=Ap03ArtifactStatus.AVAILABLE,
        sha256="d" * 64,
    )
    report_b = report_a.model_copy(update={"sha256": "e" * 64})

    assert _historical_input_state_hash((audit, golden, report_a)) == _historical_input_state_hash(
        (audit, golden, report_b)
    )
