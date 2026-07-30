"""Workflow artifact inspection and recovery policies."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from standards_atlas.adapters.docling import DoclingArtifactRepository, ExtractionState
from standards_atlas.application.workflow.models import WorkflowStage, WorkflowStep


class WorkflowRecovery:
    @staticmethod
    def _docling_extraction_state(step: WorkflowStep, project_root: Path) -> ExtractionState | None:
        """Return the persisted Docling state for a Docling conversion step."""
        if step.stage is not WorkflowStage.DOCLING:
            return None
        try:
            document_option = step.command.index("-d")
            document_key = step.command[document_option + 1]
            source = Path(step.command[document_option + 2])
        except (ValueError, IndexError):
            return None
        if not source.is_absolute():
            source = project_root / source
        repository = DoclingArtifactRepository(project_root / ".atlas")
        return repository.extraction_state(document_key, source)

    @staticmethod
    def _execution_command(
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

    @staticmethod
    def _outputs_exist(step: WorkflowStep, project_root: Path) -> bool:
        if not step.output_paths and not step.output_globs:
            return False
        paths_exist = all((project_root / path).exists() for path in step.output_paths)
        globs_exist = all(any(project_root.glob(pattern)) for pattern in step.output_globs)
        return paths_exist and globs_exist

    @staticmethod
    def _record_completion(step: WorkflowStep, project_root: Path) -> None:
        for relative_path in step.output_paths:
            if not relative_path.startswith(".atlas/workflow/"):
                continue
            marker = project_root / relative_path
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("completed\n", encoding="utf-8")

    @staticmethod
    def _remove_outputs(step: WorkflowStep, project_root: Path) -> None:
        targets = [project_root / path for path in step.output_paths]
        for pattern in step.output_globs:
            targets.extend(project_root.glob(pattern))
        for target in targets:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)

    @staticmethod
    def _alignment_requires_review(project_root: Path, document_key: str) -> bool:
        path = project_root / ".atlas" / "alignments" / document_key / "alignment.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            statistics = payload["metadata"]["statistics"]
            return bool(statistics.get("missing", 0) or statistics.get("conflicting", 0))
        except (OSError, ValueError, KeyError, TypeError):
            return True

    docling_extraction_state = _docling_extraction_state
    execution_command = _execution_command
    outputs_exist = _outputs_exist
    record_completion = _record_completion
    remove_outputs = _remove_outputs
    alignment_requires_review = _alignment_requires_review
