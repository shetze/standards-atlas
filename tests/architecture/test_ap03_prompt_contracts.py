from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.adapters.evaluation import ResourcePromptCatalog
from standards_atlas.application.prompt_workbench.context import list_context_variants

PROMPTS = Path("src/standards_atlas/resources/semantic/prompts")
TASKS = Path("src/standards_atlas/resources/semantic/tasks")


def test_ap03_b0_uses_current_assertion_tasks_and_no_legacy_relations_task() -> None:
    manifest = json.loads((PROMPTS / "ap03-b0.json").read_text(encoding="utf-8"))
    bindings = {(item["task"], item["prompt_version"]) for item in manifest["prompt_bindings"]}

    assert bindings == {
        (
            "formal-semantic-knowledge-proposal",
            "ontology-guided-assertions-source-bound-v1",
        ),
        (
            "formal-semantic-assertion-verification",
            "ontology-guided-assertion-verifier-source-bound-v1",
        ),
    }
    assert not (TASKS / "formal-semantic-knowledge-extraction").exists()


def test_current_assertion_prompt_bundles_are_discoverable_and_task_schema_bound() -> None:
    catalog = ResourcePromptCatalog(PROMPTS)
    discovered = {(item.task, item.version) for item in catalog.list_prompts()}

    for task, version in (
        (
            "formal-semantic-knowledge-proposal",
            "ontology-guided-assertions-source-bound-v1",
        ),
        (
            "formal-semantic-assertion-verification",
            "ontology-guided-assertion-verifier-source-bound-v1",
        ),
    ):
        assert (task, version) in discovered
        definition = catalog.load_prompt(task, version)
        assert definition.task_schema_version == "1.0.0"


def test_prompt_workbench_no_longer_recommends_legacy_entities_relations_task() -> None:
    recommended = {
        task for variant in list_context_variants() for task in variant.recommended_tasks
    }

    assert "formal-semantic-knowledge-extraction" not in recommended
    assert "formal-semantic-knowledge-proposal" in recommended
