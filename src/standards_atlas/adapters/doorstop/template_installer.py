"""Install packaged Doorstop HTML templates into generated hierarchies."""

from __future__ import annotations

import shutil
from importlib.resources import as_file, files
from pathlib import Path

import yaml

AVAILABLE_DOORSTOP_TEMPLATES = (
    "atlas-clean",
    "technical-blueprint",
    "midnight-focus",
)


class DoorstopTemplateInstaller:
    """Copy a versioned Standards Atlas template beside the root Doorstop document."""

    def install(self, hierarchy_root: Path, template_name: str) -> Path:
        if template_name not in AVAILABLE_DOORSTOP_TEMPLATES:
            available = ", ".join(AVAILABLE_DOORSTOP_TEMPLATES)
            raise ValueError(
                f"unknown Doorstop template {template_name!r}; choose one of: {available}"
            )
        root_document, document_directories = self._find_documents(hierarchy_root)
        for document_directory in document_directories:
            existing = document_directory / "template"
            if existing.exists():
                shutil.rmtree(existing)
        target = root_document / "template"
        resource = files("standards_atlas.resources.doorstop_templates").joinpath(template_name)
        with as_file(resource) as source:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        return target

    @staticmethod
    def _find_documents(hierarchy_root: Path) -> tuple[Path, tuple[Path, ...]]:
        configs = sorted(hierarchy_root.rglob(".doorstop.yml"))
        if not configs:
            raise FileNotFoundError(f"no Doorstop documents found below {hierarchy_root}")
        roots: list[Path] = []
        for config in configs:
            payload = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
            settings = payload.get("settings") or {}
            if not settings.get("parent"):
                roots.append(config.parent)
        if len(roots) != 1:
            raise ValueError(
                "expected exactly one root Doorstop document below "
                f"{hierarchy_root}, got {len(roots)}"
            )
        return roots[0], tuple(config.parent for config in configs)
