from pathlib import Path

import pytest

from standards_atlas.adapters.workflow import FileSystemWorkflowArtifactStore
from standards_atlas.application.workflow import (
    ArtifactPolicy,
    WorkflowExecutor,
    WorkflowPlan,
    WorkflowRecovery,
    WorkflowStage,
    WorkflowStep,
)


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...], cwd: Path) -> None:
        self.commands.append(command)


def test_evaluation_steps_wait_for_open_document_review_gate(tmp_path: Path) -> None:
    atlasdata = WorkflowStep(
        family="FAMILY",
        document="DOC",
        stage=WorkflowStage.ATLASDATA,
        command=("atlasdata",),
        artifact_policy=ArtifactPolicy.REVIEW,
        manual_gate=True,
    )
    corpus = WorkflowStep(
        family="evaluation",
        document="corpus",
        stage=WorkflowStage.CORPUS_BUILD,
        command=("corpus-build",),
        artifact_policy=ArtifactPolicy.DERIVED,
    )
    matrix = WorkflowStep(
        family="evaluation",
        document="matrix",
        stage=WorkflowStage.QUALIFICATION_MATRIX,
        command=("qualification-matrix",),
        artifact_policy=ArtifactPolicy.DERIVED,
    )
    detail = WorkflowStep(
        family="evaluation",
        document="matrix-applicability-detail",
        stage=WorkflowStage.APPLICABILITY_DETAIL_ENRICHMENT,
        command=("applicability-detail-enrich",),
        artifact_policy=ArtifactPolicy.DERIVED,
    )
    semantic = WorkflowStep(
        family="evaluation",
        document="matrix-semantic-extraction",
        stage=WorkflowStage.SEMANTIC_EXTRACTION_QUALIFICATION,
        command=("semantic-extraction-qualification",),
        artifact_policy=ArtifactPolicy.DERIVED,
    )
    archive = WorkflowStep(
        family="evaluation",
        document="matrix-archive",
        stage=WorkflowStage.QUALIFICATION_ARCHIVE,
        command=("qualification-archive",),
        artifact_policy=ArtifactPolicy.REVIEW,
    )
    plan = WorkflowPlan(
        ("FAMILY",),
        (atlasdata, corpus, matrix, detail, semantic, archive),
    )
    runner = RecordingRunner()
    executor = WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))

    result = executor.execute(plan, project_root=tmp_path, runner=runner)

    assert runner.commands == [("atlasdata",)]
    assert result.blocked_families == ("FAMILY",)
    assert not result.completed


class FailingOnceRunner:
    def __init__(self, failing_command: tuple[str, ...]) -> None:
        self.failing_command = failing_command
        self.commands: list[tuple[str, ...]] = []
        self.failed = False

    def run(self, command: tuple[str, ...], cwd: Path) -> None:
        self.commands.append(command)
        if command == self.failing_command and not self.failed:
            self.failed = True
            raise RuntimeError("simulated export failure")


def test_resume_retries_failed_export_without_repeating_completed_step(tmp_path: Path) -> None:
    prepared = WorkflowStep(
        family="FAMILY",
        document="DOC",
        stage=WorkflowStage.CONTEXT_ENRICHMENT,
        command=("prepare",),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=(".atlas/work/workflow/context-enrichment/DOC.complete",),
    )
    export = WorkflowStep(
        family="FAMILY",
        document="FAMILY",
        stage=WorkflowStage.MARKDOWN,
        command=("export-markdown",),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=(".atlas/work/workflow/markdown/FAMILY.complete",),
    )
    plan = WorkflowPlan(("FAMILY",), (prepared, export))
    executor = WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    first_runner = FailingOnceRunner(("export-markdown",))

    with pytest.raises(RuntimeError, match="simulated export failure"):
        executor.execute(plan, project_root=tmp_path, runner=first_runner)

    assert first_runner.commands == [("prepare",), ("export-markdown",)]
    assert (tmp_path / prepared.output_paths[0]).is_file()
    assert not (tmp_path / export.output_paths[0]).exists()

    resumed_runner = RecordingRunner()
    result = executor.execute(plan, project_root=tmp_path, runner=resumed_runner)

    assert resumed_runner.commands == [("export-markdown",)]
    assert result.executed_steps == (export,)


def test_resume_survives_normal_work_cleanup(tmp_path: Path) -> None:
    prepared = WorkflowStep(
        family="FAMILY",
        document="DOC",
        stage=WorkflowStage.CONTEXT_ENRICHMENT,
        command=("prepare", "--mode", "current"),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=(".atlas/work/workflow/context-enrichment/DOC.complete",),
    )
    failed = WorkflowStep(
        family="evaluation",
        document="matrix-semantic-extraction",
        stage=WorkflowStage.SEMANTIC_EXTRACTION_QUALIFICATION,
        command=("qualify",),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=(".atlas/work/workflow/qualification/extraction.complete",),
    )
    plan = WorkflowPlan(("FAMILY",), (prepared, failed))
    executor = WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    first = FailingOnceRunner(("qualify",))

    with pytest.raises(RuntimeError):
        executor.execute(plan, project_root=tmp_path, runner=first)

    from standards_atlas.application.workspace import WorkspaceLayout

    WorkspaceLayout(tmp_path).clear_work(preserve_workflow=True)
    resumed = RecordingRunner()
    executor.execute(plan, project_root=tmp_path, runner=resumed)

    assert resumed.commands == [("qualify",)]


def test_changed_step_command_invalidates_workflow_checkpoint(tmp_path: Path) -> None:
    old = WorkflowStep(
        family="evaluation",
        document="matrix",
        stage=WorkflowStage.QUALIFICATION_MATRIX,
        command=("matrix",),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=(".atlas/work/workflow/qualification/matrix.complete",),
    )
    fresh = WorkflowStep(
        family="evaluation",
        document="matrix",
        stage=WorkflowStage.QUALIFICATION_MATRIX,
        command=("matrix", "--fresh"),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=old.output_paths,
    )
    executor = WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    executor.execute(
        WorkflowPlan(("evaluation",), (old,)),
        project_root=tmp_path,
        runner=RecordingRunner(),
    )

    runner = RecordingRunner()
    executor.execute(WorkflowPlan(("evaluation",), (fresh,)), project_root=tmp_path, runner=runner)

    assert runner.commands == [("matrix", "--fresh")]


def test_resume_reuses_completed_applicability_detail_stage(tmp_path: Path) -> None:
    matrix = WorkflowStep(
        family="evaluation",
        document="matrix",
        stage=WorkflowStage.QUALIFICATION_MATRIX,
        command=("qualification-matrix",),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=(".atlas/work/workflow/qualification/matrix.complete",),
    )
    detail = WorkflowStep(
        family="evaluation",
        document="matrix-applicability-detail",
        stage=WorkflowStage.APPLICABILITY_DETAIL_ENRICHMENT,
        command=("applicability-detail-enrich",),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=(".atlas/work/workflow/qualification/detail.complete",),
    )
    archive = WorkflowStep(
        family="evaluation",
        document="matrix-archive",
        stage=WorkflowStage.QUALIFICATION_ARCHIVE,
        command=("qualification-archive",),
        artifact_policy=ArtifactPolicy.REVIEW,
        output_paths=(".atlas/work/workflow/qualification/archive.complete",),
    )
    plan = WorkflowPlan(("evaluation",), (matrix, detail, archive))
    executor = WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore()))
    first = FailingOnceRunner(("qualification-archive",))

    with pytest.raises(RuntimeError, match="simulated export failure"):
        executor.execute(plan, project_root=tmp_path, runner=first)

    assert first.commands == [
        ("qualification-matrix",),
        ("applicability-detail-enrich",),
        ("qualification-archive",),
    ]
    assert (tmp_path / detail.output_paths[0]).is_file()

    resumed = RecordingRunner()
    result = executor.execute(plan, project_root=tmp_path, runner=resumed)

    assert resumed.commands == [("qualification-archive",)]
    assert result.executed_steps == (archive,)
