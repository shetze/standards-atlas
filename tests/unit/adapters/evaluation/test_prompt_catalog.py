from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.adapters.evaluation.prompt_catalog import ResourcePromptCatalog


def _prompt(root: Path, task: str, version: str, *, complete: bool = True) -> None:
    path = root / task / version
    path.mkdir(parents=True)
    (path / "prompt.json").write_text(
        json.dumps({"description": "Prompt description"}), encoding="utf-8"
    )
    (path / "system.txt").write_text("System", encoding="utf-8")
    (path / "user.txt").write_text("Clause: {content}", encoding="utf-8")
    if complete:
        (path / "schema.json").write_text('{"type":"object"}', encoding="utf-8")


def test_discovers_only_complete_prompt_bundles(tmp_path: Path) -> None:
    _prompt(tmp_path, "classification", "1.0.0")
    _prompt(tmp_path, "classification", "draft", complete=False)
    catalog = ResourcePromptCatalog(tmp_path)

    assert catalog.list_prompts()[0].model_dump() == {
        "task": "classification",
        "version": "1.0.0",
        "description": "Prompt description",
        "placeholders": ("content",),
    }
    assert catalog.load_prompt("classification", "1.0.0").system_prompt == "System"
