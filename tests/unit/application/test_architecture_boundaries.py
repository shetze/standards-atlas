"""Architecture guardrails for the hexagonal application core."""

from __future__ import annotations

import ast
from pathlib import Path


def test_application_layer_does_not_import_adapters() -> None:
    root = Path("src/standards_atlas/application")
    violations: list[str] = []

    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "standards_atlas.adapters" or module.startswith(
                    "standards_atlas.adapters."
                ):
                    violations.append(f"{path}:{node.lineno}: {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "standards_atlas.adapters" or alias.name.startswith(
                        "standards_atlas.adapters."
                    ):
                        violations.append(f"{path}:{node.lineno}: {alias.name}")

    assert violations == []
