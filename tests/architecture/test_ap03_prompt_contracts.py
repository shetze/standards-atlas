from __future__ import annotations

import hashlib
import json
import re
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


def test_ap03_p1_p2_share_one_versioned_policy_without_changing_b0() -> None:
    from standards_atlas.application.evaluation.source_bound_prompt import (
        semantic_prompt_repository,
    )

    repository = semantic_prompt_repository()
    baseline = repository.load(
        "formal-semantic-knowledge-proposal", "ontology-guided-assertions-source-bound-v1"
    )
    extractor_p1 = repository.load("formal-semantic-knowledge-proposal", "engineering-policy-v1")
    verifier_p1 = repository.load(
        "formal-semantic-assertion-verification", "engineering-policy-verifier-v1"
    )
    extractor_p2 = repository.load(
        "formal-semantic-knowledge-proposal", "engineering-policy-contrast-v1"
    )
    verifier_p2 = repository.load(
        "formal-semantic-assertion-verification", "engineering-policy-verifier-contrast-v1"
    )

    assert baseline.policy_id is None
    assert baseline.example_set_id is None
    assert extractor_p1.qualification_status == verifier_p1.qualification_status == "unqualified"
    assert extractor_p2.qualification_status == verifier_p2.qualification_status == "unqualified"
    assert extractor_p1.baseline_id == verifier_p1.baseline_id == "B0-AP02"
    assert extractor_p2.baseline_id == verifier_p2.baseline_id == "B0-AP02"
    assert extractor_p1.variant_id == verifier_p1.variant_id == "P1"
    assert extractor_p2.variant_id == verifier_p2.variant_id == "P2"
    assert extractor_p1.policy_id == verifier_p1.policy_id == "engineering-assertion-extraction"
    assert extractor_p1.policy_version == verifier_p1.policy_version == "1.0.0"
    assert extractor_p1.policy_sha256 == verifier_p1.policy_sha256
    assert extractor_p2.policy_sha256 == verifier_p2.policy_sha256 == extractor_p1.policy_sha256
    assert extractor_p1.example_set_id is None
    assert verifier_p1.example_set_id is None
    assert extractor_p2.example_set_id == verifier_p2.example_set_id == "engineering-contrast"
    assert extractor_p2.example_set_partition == "public-synthetic-development"
    assert extractor_p2.example_set_sha256 == verifier_p2.example_set_sha256

    frozen = json.loads((PROMPTS / "ap03-b0.json").read_text(encoding="utf-8"))
    frozen_extractor = next(
        item for item in frozen["prompt_bindings"] if item["role"] == "extractor"
    )
    raw_baseline_system = (
        PROMPTS
        / "formal-semantic-knowledge-proposal"
        / "ontology-guided-assertions-source-bound-v1"
        / "system.txt"
    ).read_bytes()
    assert (
        hashlib.sha256(raw_baseline_system).hexdigest()
        == frozen_extractor["files"]["system_sha256"]
    )


def test_ap03_variant_manifest_binds_only_public_synthetic_examples_and_no_clause_rules() -> None:
    root = Path("src/standards_atlas/resources/semantic")
    manifest = json.loads(
        (root / "experiments/ap03-engineering-prompt-variants-v1.json").read_text(encoding="utf-8")
    )
    variants = {item["id"]: item for item in manifest["variants"]}

    assert set(variants) == {"P1", "P2"}
    assert manifest["qualification_status"] == "unqualified"
    assert variants["P1"]["example_set"] is None
    assert variants["P2"]["example_set"]["source_class"] == "public_synthetic"
    assert variants["P2"]["example_set"]["partition"] == "public-synthetic-development"
    assert manifest["constraints"] == {
        "private_standard_text_in_resources": False,
        "clause_id_specific_rules": False,
        "schema_change": False,
        "source_policy_change": False,
    }
    policy = (root / manifest["shared_policy"]["path"]).read_text(encoding="utf-8")
    examples = (root / variants["P2"]["example_set"]["path"]).read_text(encoding="utf-8")
    assert (
        hashlib.sha256(policy.strip().encode("utf-8")).hexdigest()
        == manifest["shared_policy"]["sha256"]
    )
    assert (
        hashlib.sha256(examples.strip().encode("utf-8")).hexdigest()
        == variants["P2"]["example_set"]["sha256"]
    )
    assert all(f"R{number:02d}" in policy for number in range(1, 15))

    clause_id_pattern = re.compile(r"clause-[0-9a-f]{8,}", re.IGNORECASE)
    assert clause_id_pattern.search(policy) is None
    assert clause_id_pattern.search(examples) is None
