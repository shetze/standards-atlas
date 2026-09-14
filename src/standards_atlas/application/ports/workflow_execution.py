"""Outbound ports required by workflow execution and run reporting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from standards_atlas.application.workflow.models import WorkflowOperation


class WorkflowOperationRunner(Protocol):
    """Execute one typed workflow operation below a project root."""

    def run(self, operation: WorkflowOperation, cwd: Path) -> None: ...


@dataclass(frozen=True)
class RepositoryIdentity:
    """Repository identity captured for an auditable workflow run."""

    revision: str | None
    dirty: bool | None


class RepositoryIdentityProvider(Protocol):
    """Read source-control identity without coupling application code to Git."""

    def identify(self, root: Path) -> RepositoryIdentity: ...
