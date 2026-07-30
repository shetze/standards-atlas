"""Ports used to inspect and mutate workflow artifacts."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from standards_atlas.application.workflow.models import WorkflowStep


class ExtractionState(StrEnum):
    """Relationship between a persisted extraction and its source file."""

    MISSING = "missing"
    CURRENT = "current"
    STALE = "stale"
    INCOMPLETE = "incomplete"


class WorkflowArtifactStore(Protocol):
    """Technical artifact operations required by workflow recovery policy."""

    def docling_extraction_state(
        self, step: WorkflowStep, project_root: Path
    ) -> ExtractionState | None: ...

    def outputs_exist(self, step: WorkflowStep, project_root: Path) -> bool: ...

    def record_completion(self, step: WorkflowStep, project_root: Path) -> None: ...

    def remove_outputs(self, step: WorkflowStep, project_root: Path) -> None: ...

    def alignment_requires_review(self, project_root: Path, document_key: str) -> bool: ...
