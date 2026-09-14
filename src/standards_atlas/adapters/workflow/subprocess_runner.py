"""Subprocess adapter for typed workflow operations."""

from __future__ import annotations

import subprocess
from pathlib import Path

from standards_atlas.adapters.workflow.cli_renderer import CliWorkflowOperationRenderer
from standards_atlas.application.workflow.models import WorkflowOperation


class SubprocessWorkflowOperationRunner:
    """Render and execute a workflow operation as a checked child process."""

    def __init__(self, renderer: CliWorkflowOperationRenderer | None = None) -> None:
        self._renderer = renderer or CliWorkflowOperationRenderer()

    def run(self, operation: WorkflowOperation, cwd: Path) -> None:
        command = self._renderer.render(operation)
        subprocess.run(command, cwd=cwd, check=True)  # noqa: S603
