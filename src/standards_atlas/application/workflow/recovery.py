"""Workflow recovery policies independent of artifact persistence."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.application.ports import ExtractionState, WorkflowArtifactStore
from standards_atlas.application.workflow.models import WorkflowStage, WorkflowStep


class WorkflowRecovery:
    """Apply recovery policy using an injected technical artifact store."""

    def __init__(self, artifacts: WorkflowArtifactStore) -> None:
        self._artifacts = artifacts

    def docling_extraction_state(
        self, step: WorkflowStep, project_root: Path
    ) -> ExtractionState | None:
        return self._artifacts.docling_extraction_state(step, project_root)

    @staticmethod
    def execution_command(
        step: WorkflowStep, docling_state: ExtractionState | None
    ) -> tuple[str, ...]:
        """Add repair semantics only for an incomplete Docling extraction."""
        if (
            step.stage is WorkflowStage.DOCLING
            and docling_state is ExtractionState.INCOMPLETE
            and "--overwrite" not in step.command
        ):
            return (*step.command, "--overwrite")
        return step.command

    def outputs_exist(self, step: WorkflowStep, project_root: Path) -> bool:
        return self._artifacts.outputs_exist(step, project_root)

    def record_completion(self, step: WorkflowStep, project_root: Path) -> None:
        self._artifacts.record_completion(step, project_root)

    def remove_outputs(self, step: WorkflowStep, project_root: Path) -> None:
        self._artifacts.remove_outputs(step, project_root)

    def alignment_requires_review(self, project_root: Path, document_key: str) -> bool:
        return self._artifacts.alignment_requires_review(project_root, document_key)
