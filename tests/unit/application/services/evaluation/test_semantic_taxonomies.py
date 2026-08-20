from pathlib import Path

from standards_atlas.application.semantic_qualification.proposals import SemanticTaskRepository
from standards_atlas.application.semantic_qualification.taxonomies import SemanticTaxonomyRepository

SEMANTIC_ROOT = Path("src/standards_atlas/resources/semantic")


def test_semantic_profile_task_composes_independently_versioned_taxonomies() -> None:
    task, _ = SemanticTaskRepository(SEMANTIC_ROOT / "tasks").load(
        "semantic-profile-classification", "2.1.0"
    )

    assert task.taxonomies["statement_functions"].version == "2.0.0"
    assert task.taxonomies["knowledge_kinds"].version == "2.1.0"
    assert task.taxonomies["process_functions"].version == "1.0.0"
    assert task.taxonomies["applicability_functions"].version == "1.1.0"
    assert task.taxonomies["responsibility_functions"].version == "1.0.0"
    assert "warning" in task.taxonomy
    assert "technique_or_measure" in task.knowledge_taxonomy


def test_legacy_multidimensional_task_is_explicit_alias_of_semantic_profile() -> None:
    task, _ = SemanticTaskRepository(SEMANTIC_ROOT / "tasks").load(
        "statement-function-classification", "2.1.0"
    )

    assert task.canonical_task == "semantic-profile-classification"


def test_semantic_taxonomy_identity_is_independent_from_task_version() -> None:
    taxonomy = SemanticTaxonomyRepository(SEMANTIC_ROOT / "taxonomies").load(
        "applicability-functions", "1.1.0"
    )

    assert taxonomy.dimension == "applicability_functions"
    assert "exception over exclusion" in taxonomy.semantics["tie_break_rules"][0]
