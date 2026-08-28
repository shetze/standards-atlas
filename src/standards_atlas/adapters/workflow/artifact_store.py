"""Filesystem implementation of workflow artifact operations."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from standards_atlas.adapters.docling import DoclingArtifactRepository
from standards_atlas.adapters.filesystem.composed_document_view_repository import (
    CURRENT_COMPOSED_DOCUMENT_VIEW_SCHEMA_VERSION,
)
from standards_atlas.adapters.filesystem.document_repository import (
    CURRENT_DOCUMENT_SCHEMA_VERSION,
)
from standards_atlas.application.ports import ExtractionState
from standards_atlas.application.workflow.models import WorkflowStage, WorkflowStep


class FileSystemWorkflowArtifactStore:
    """Inspect and mutate workflow artifacts below a project root."""

    def docling_extraction_state(
        self, step: WorkflowStep, project_root: Path
    ) -> ExtractionState | None:
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
        repository = DoclingArtifactRepository(project_root / ".atlas" / "data")
        return repository.extraction_state(document_key, source)

    def outputs_exist(self, step: WorkflowStep, project_root: Path) -> bool:
        if not step.output_paths and not step.output_globs:
            return False
        paths_exist = all(
            self._output_is_current(project_root / path, path) for path in step.output_paths
        )
        globs_exist = all(any(project_root.glob(pattern)) for pattern in step.output_globs)
        return paths_exist and globs_exist

    @staticmethod
    def _output_is_current(path: Path, relative_path: str) -> bool:
        if not path.exists():
            return False
        normalized = relative_path.replace("\\", "/")
        if (
            normalized.startswith(".atlas/data/documents/")
            or normalized.startswith(".atlas/work/family-sources/documents/")
        ) and normalized.endswith(".json"):
            return _json_schema_version(path) == CURRENT_DOCUMENT_SCHEMA_VERSION
        if normalized.startswith(".atlas/work/composed-documents/") and normalized.endswith(
            ".json"
        ):
            return _json_schema_version(path) == CURRENT_COMPOSED_DOCUMENT_VIEW_SCHEMA_VERSION
        return True

    def record_completion(self, step: WorkflowStep, project_root: Path) -> None:
        for relative_path in step.output_paths:
            if not relative_path.startswith(".atlas/work/workflow/"):
                continue
            marker = project_root / relative_path
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("completed\n", encoding="utf-8")

    def remove_outputs(self, step: WorkflowStep, project_root: Path) -> None:
        targets = [project_root / path for path in step.output_paths]
        for pattern in step.output_globs:
            targets.extend(project_root.glob(pattern))
        for target in targets:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)

    def alignment_requires_review(self, project_root: Path, document_key: str) -> bool:
        path = project_root / ".atlas" / "data" / "alignments" / document_key / "alignment.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            statistics = payload["metadata"]["statistics"]
            return bool(statistics.get("missing", 0) or statistics.get("conflicting", 0))
        except (OSError, ValueError, KeyError, TypeError):
            return True


def _json_schema_version(path: Path) -> object | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload.get("schema_version")
