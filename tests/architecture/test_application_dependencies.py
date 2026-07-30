"""Architecture guards for inward-pointing application dependencies."""

from __future__ import annotations

import ast
from pathlib import Path

APPLICATION_ROOT = Path("src/standards_atlas/application")


def test_refactored_application_boundaries_do_not_import_adapters() -> None:
    guarded = (
        APPLICATION_ROOT / "services" / "document_normalization_service.py",
        APPLICATION_ROOT / "services" / "markdown_export_service.py",
        APPLICATION_ROOT / "workflow" / "recovery.py",
        APPLICATION_ROOT / "workflow" / "executor.py",
    )

    violations: list[str] = []
    for path in guarded:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("standards_atlas.adapters"):
                    violations.append(f"{path}:{node.lineno} imports {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("standards_atlas.adapters"):
                        violations.append(f"{path}:{node.lineno} imports {alias.name}")

    assert violations == []
