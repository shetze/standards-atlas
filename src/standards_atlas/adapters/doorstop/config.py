"""Configuration for Doorstop exports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DoorstopExportConfig:
    workspace: Path = Path(".atlas/doorstop")

    prefix: str | None = None
    digits: int = 8
    separator: str = "-"
    item_format: str = "yaml"
    parent: str | None = None

    replace_existing: bool = True
    validate_after_export: bool = True
    initialize_git_repository: bool = True
