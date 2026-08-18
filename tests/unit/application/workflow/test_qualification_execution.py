from pathlib import Path

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
