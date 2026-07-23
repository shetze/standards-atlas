"""Manage explicit AtlasData baseline maturity transitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from standards_atlas.adapters.atlasdata.metadata import (
    AtlasDataLifecycleStatus,
    parse_metadata,
)
_ALLOWED = {
    AtlasDataLifecycleStatus.PROPOSED: AtlasDataLifecycleStatus.REVIEWED,
    AtlasDataLifecycleStatus.REVIEWED: AtlasDataLifecycleStatus.PUBLISHED,
}


class AtlasDataLifecycleError(RuntimeError):
    """Raised for invalid AtlasData lifecycle operations."""


@dataclass(frozen=True)
class AtlasDataLifecycleResult:
    path: Path
    previous: AtlasDataLifecycleStatus
    current: AtlasDataLifecycleStatus


class AtlasDataLifecycleService:
    """Advance an AtlasData baseline through its review lifecycle."""

    def transition(
        self, path: Path, target: AtlasDataLifecycleStatus
    ) -> AtlasDataLifecycleResult:
        text = path.read_text(encoding="utf-8")
        previous = parse_metadata(text).lifecycle_status
        if previous == target:
            return AtlasDataLifecycleResult(path, previous, target)
        expected = _ALLOWED.get(previous)
        if expected != target:
            raise AtlasDataLifecycleError(
                f"Invalid AtlasData lifecycle transition: {previous.value} -> {target.value}. "
                "Allowed progression is proposed -> reviewed -> published."
            )
        lines = text.splitlines()
        replaced = False
        for index, line in enumerate(lines):
            if line.strip().startswith(("lifecycle_status=", "lifecycleStatus=")):
                lines[index] = f'lifecycle_status="{target.value}"'
                replaced = True
                break
            if line.strip().startswith("structure="):
                lines.insert(index, f'lifecycle_status="{target.value}"')
                replaced = True
                break
        if not replaced:
            raise AtlasDataLifecycleError(f"AtlasData structure block not found: {path}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return AtlasDataLifecycleResult(path, previous, target)
