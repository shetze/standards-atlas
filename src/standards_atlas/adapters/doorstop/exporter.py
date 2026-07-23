"""Doorstop export adapter."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from standards_atlas.adapters.artifact_lineage import write_directory_lineage_manifest
from standards_atlas.adapters.doorstop.config import DoorstopExportConfig
from standards_atlas.adapters.doorstop.document_renderer import (
    DoorstopDocumentRenderer,
)
from standards_atlas.adapters.doorstop.id_generator import DoorstopIdContext
from standards_atlas.adapters.doorstop.item_mapper import DoorstopItemMapper
from standards_atlas.adapters.doorstop.item_renderer import DoorstopItemRenderer
from standards_atlas.adapters.doorstop.models import DoorstopDocumentModel
from standards_atlas.domain.model import EngineeringDocument


class DoorstopExporter:
    """Export EngineeringDocument objects to a Doorstop workspace."""

    def __init__(
        self,
        config: DoorstopExportConfig | None = None,
    ) -> None:
        self._config = config or DoorstopExportConfig()
        self._document_renderer = DoorstopDocumentRenderer()
        self._item_renderer = DoorstopItemRenderer()

    def export_document(
        self,
        document: EngineeringDocument,
        target: Path | None = None,
    ) -> Path:
        prefix = self._config.prefix or _normalize_prefix(document.key.value)

        target_directory = (
            target if target is not None else self._config.workspace / document.key.value
        )

        self._config.workspace.mkdir(parents=True, exist_ok=True)
        self._prepare_target(target_directory)

        if self._config.initialize_git_repository:
            self._ensure_git_repository(self._config.workspace)

        document_model = DoorstopDocumentModel(
            prefix=prefix,
            digits=self._config.digits,
            separator=self._config.separator,
            item_format=self._config.item_format,
            parent=self._config.parent,
            target=target_directory,
        )

        self._document_renderer.render(document_model)

        mapper = DoorstopItemMapper(
            prefix=prefix,
            separator=self._config.separator,
            id_context=DoorstopIdContext(
                digits=self._config.digits,
            ),
        )

        for item in mapper.map_document(document):
            self._item_renderer.render(
                item,
                target_directory,
            )

        if self._config.validate_after_export:
            self._validate(self._config.workspace)

        write_directory_lineage_manifest(
            target_directory,
            document,
            kind="doorstop_export",
        )
        return target_directory

    def _prepare_target(self, target: Path) -> None:
        if target.exists():
            if not self._config.replace_existing:
                raise FileExistsError(f"Doorstop target already exists: {target}")

            shutil.rmtree(target)

        target.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate(target: Path) -> None:
        result = subprocess.run(
            ["doorstop"],
            cwd=target,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Doorstop validation failed:\n{result.stdout}\n{result.stderr}")

    @staticmethod
    def _ensure_git_repository(target: Path) -> None:
        """Ensure that the Doorstop target is a Git working copy."""
        git_directory = target / ".git"

        if git_directory.exists():
            return

        result = subprocess.run(
            ["git", "init", "--quiet", "."],
            cwd=target,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Could not initialize Git repository for Doorstop:\n"
                f"{result.stdout}\n{result.stderr}"
            )


def _normalize_prefix(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())
