"""Canonical storage layout and lifecycle for a Standards Atlas project."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorkspaceLayout:
    """Resolve project-owned storage classes from one project root.

    ``.atlas/data`` contains persistent machine-facing state, ``.atlas/cache``
    disposable acceleration artifacts, ``.atlas/work`` the retained scratch
    space of the most recent workflow, and ``local`` persistent human-facing
    artifacts. Human review artifacts are always rooted below ``local/review``.
    """

    project_root: Path = Path(".")

    @property
    def atlas_root(self) -> Path:
        return self.project_root / ".atlas"

    @property
    def data(self) -> Path:
        return self.atlas_root / "data"

    @property
    def cache(self) -> Path:
        return self.atlas_root / "cache"

    @property
    def work(self) -> Path:
        return self.atlas_root / "work"

    @property
    def local(self) -> Path:
        return self.project_root / "local"

    @property
    def review(self) -> Path:
        return self.local / "review"

    @property
    def doorstop_work(self) -> Path:
        """Return the rebuildable Doorstop adapter workspace."""
        return self.work / "doorstop"

    def doorstop_hierarchy(self, hierarchy_key: str) -> Path:
        """Return one hierarchy root below the Doorstop work area."""
        return self.doorstop_work / hierarchy_key

    @property
    def evaluation_data(self) -> Path:
        return self.data / "evaluation"

    @property
    def evaluation_corpora(self) -> Path:
        return self.evaluation_data / "corpora"

    @property
    def evaluation_runs(self) -> Path:
        return self.evaluation_data / "runs"

    @property
    def evaluation_qualification(self) -> Path:
        return self.evaluation_data / "qualification"

    @property
    def llm_cache(self) -> Path:
        return self.cache / "llm"

    def clear_work(self) -> None:
        """Remove retained scratch artifacts from previous workflow execution."""
        shutil.rmtree(self.work, ignore_errors=True)

    def clear_cache(self) -> None:
        """Remove all reproducible cache artifacts."""
        shutil.rmtree(self.cache, ignore_errors=True)

    def clear_data(self) -> None:
        """Remove persistent machine-facing state.

        Callers must make the destructive intent explicit before invoking this
        method. Human-facing ``local`` artifacts are deliberately out of scope.
        """
        shutil.rmtree(self.data, ignore_errors=True)
