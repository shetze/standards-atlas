from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_task_schema_binding_rejects_divergent_prompt_schema(tmp_path: Path) -> None:
    prompt_root = tmp_path / "prompts"
    task_root = tmp_path / "tasks"
    path = prompt_root / "formal-semantic-knowledge-proposal" / "baseline"
    path.mkdir(parents=True)
    (path / "prompt.json").write_text(
        json.dumps(
            {
                "task": "formal-semantic-knowledge-proposal",
                "version": "baseline",
                "task_schema_version": "1.0.0",
            }
        ),
        encoding="utf-8",
    )
    (path / "system.txt").write_text("System", encoding="utf-8")
    (path / "user.txt").write_text("{request_json}", encoding="utf-8")
    (path / "schema.json").write_text('{"type":"object"}', encoding="utf-8")

    task = task_root / "formal-semantic-knowledge-proposal" / "1.0.0"
    task.mkdir(parents=True)
    (task / "task.yaml").write_text(
        "schema_version: 1\ntask: formal-semantic-knowledge-proposal\nversion: 1.0.0\n",
        encoding="utf-8",
    )
    (task / "schema.json").write_text('{"type":"array"}', encoding="utf-8")

    catalog = ResourcePromptCatalog(prompt_root)
    with pytest.raises(ValueError, match="prompt schema differs from task-owned schema"):
        catalog.load_prompt("formal-semantic-knowledge-proposal", "baseline")


def test_task_schema_binding_rejects_incomplete_bundle(tmp_path: Path) -> None:
    prompt_root = tmp_path / "prompts"
    path = prompt_root / "formal-semantic-knowledge-proposal" / "baseline"
    path.mkdir(parents=True)
    (path / "prompt.json").write_text("{}", encoding="utf-8")

    catalog = ResourcePromptCatalog(prompt_root)
    with pytest.raises(ValueError, match="incomplete prompt bundle"):
        catalog.load_prompt("formal-semantic-knowledge-proposal", "baseline")
