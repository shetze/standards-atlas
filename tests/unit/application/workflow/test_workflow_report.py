from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from standards_atlas.application.ports import RepositoryIdentity
from standards_atlas.application.workflow import (
    ArtifactPolicy,
    WorkflowExecutionResult,
    WorkflowOperation,
    WorkflowOperationKind,
    WorkflowPlan,
    WorkflowRunReporter,
    WorkflowStage,
    WorkflowStep,
)


class StaticRepositoryIdentityProvider:
    def identify(self, root: Path) -> RepositoryIdentity:
        return RepositoryIdentity(revision=None, dirty=None)


def reporter() -> WorkflowRunReporter:
    return WorkflowRunReporter(StaticRepositoryIdentityProvider())


def test_completed_run_report_records_plan_and_artifact_hashes(tmp_path: Path) -> None:
    manifest = tmp_path / "manifests" / "standards.yaml"
    manifest.parent.mkdir()
    manifest.write_text("manifest_type: standards\nschema_version: 1\n", encoding="utf-8")
    artifact = tmp_path / ".atlas" / "data" / "normalized" / "DOC" / "document.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"value":1}\n', encoding="utf-8")
    step = WorkflowStep(
        family="FAMILY",
        document="DOC",
        stage=WorkflowStage.NORMALIZE,
        operation=WorkflowOperation.create(
            WorkflowOperationKind.NORMALIZE_DOCUMENT, document="DOC"
        ),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=(".atlas/data/normalized/DOC/document.json",),
    )
    plan = WorkflowPlan(("FAMILY",), (step,))
    result = WorkflowExecutionResult((step,), (), ())

    report_json, report_md = reporter().write(
        plan,
        result,
        project_root=tmp_path,
        manifest_paths=(manifest,),
        now=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )

    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["schema_version"] == 4
    assert payload["task"] == "documents"
    assert payload["manifests"] == ["manifests/standards.yaml"]
    assert payload["run_id"].startswith("20260724T120000Z-")
    assert payload["steps"][0]["disposition"] == "executed"
    assert payload["steps"][0]["operation"]["kind"] == "normalize-document"
    assert payload["steps"][0]["artifacts"][0]["path"] == (
        ".atlas/data/normalized/DOC/document.json"
    )
    assert len(payload["steps"][0]["artifacts"][0]["sha256"]) == 64
    assert "Deterministic derivation" in report_md.read_text(encoding="utf-8")


def test_report_marks_existing_outputs_as_reused(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("manifest_type: standards\nschema_version: 1\n", encoding="utf-8")
    output = tmp_path / "local" / "exports" / "markdown" / "DOC.md"
    output.parent.mkdir(parents=True)
    output.write_text("# Document\n", encoding="utf-8")
    step = WorkflowStep(
        family="FAMILY",
        document="DOC",
        stage=WorkflowStage.MARKDOWN,
        operation=WorkflowOperation.create(
            WorkflowOperationKind.DOCUMENT_EXPORT_MARKDOWN, document="DOC"
        ),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=("local/exports/markdown/DOC.md",),
    )
    plan = WorkflowPlan(("FAMILY",), (step,))
    result = WorkflowExecutionResult((), (), ())

    report_json, _ = reporter().write(
        plan,
        result,
        project_root=tmp_path,
        manifest_paths=(manifest,),
        now=lambda: datetime(2026, 7, 24, 12, 1, tzinfo=UTC),
    )

    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["steps"][0]["disposition"] == "reused"
    assert payload["summary"]["reused_steps"] == 1


def test_paused_run_does_not_receive_completion_report(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("manifest_type: standards\nschema_version: 1\n", encoding="utf-8")
    result = WorkflowExecutionResult((), ("DOC",), ())

    with pytest.raises(ValueError, match="completed runs"):
        reporter().write(
            WorkflowPlan(("FAMILY",), ()),
            result,
            project_root=tmp_path,
            manifest_paths=(manifest,),
        )
