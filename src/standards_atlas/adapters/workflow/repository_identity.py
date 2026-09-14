"""Git-backed repository identity adapter for workflow run reports."""

from __future__ import annotations

import subprocess
from pathlib import Path

from standards_atlas.application.ports.workflow_execution import RepositoryIdentity


class GitRepositoryIdentityProvider:
    """Resolve the current Git revision and dirty state when available."""

    def identify(self, root: Path) -> RepositoryIdentity:
        revision = self._command(root, "rev-parse", "HEAD")
        status = self._command(root, "status", "--porcelain")
        return RepositoryIdentity(
            revision=revision,
            dirty=bool(status) if status is not None else None,
        )

    @staticmethod
    def _command(root: Path, *args: str) -> str | None:
        try:
            return subprocess.run(  # noqa: S603
                ("git", *args), cwd=root, check=True, capture_output=True, text=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None
