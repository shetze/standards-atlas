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
    plan = WorkflowPlan(("FAMILY",), (atlasdata, corpus, matrix))
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
        stage=WorkflowStage.SEMANTIC_ENRICHMENT,
        command=("prepare",),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=(".atlas/work/workflow/semantic-enrichment/DOC.complete",),
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
