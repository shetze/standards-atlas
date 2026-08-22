from pathlib import Path

from standards_atlas.adapters.ontologies import ResourceOntologyDefinitionRepository
from standards_atlas.application.semantic_qualification.proposals import SemanticTaskRepository

SEMANTIC_ROOT = Path("src/standards_atlas/resources/semantic")


def test_semantic_profile_task_composes_independently_versioned_ontologies() -> None:
    task, _ = SemanticTaskRepository(SEMANTIC_ROOT / "tasks").load(
        "semantic-profile-classification", "2.2.0"
    )

    assert task.ontologies["statement_functions"].version == "2.0.0"
    assert task.ontologies["knowledge_kinds"].version == "2.1.0"
    assert task.ontologies["process_functions"].version == "1.0.0"
    assert task.ontologies["applicability_functions"].version == "1.1.0"
    assert task.ontologies["role_relation_types"].version == "1.0.0"
    assert "warning" in task.taxonomy
    assert "technique_or_measure" in task.knowledge_taxonomy


def test_legacy_multidimensional_task_is_explicit_alias_of_semantic_profile() -> None:
    task, _ = SemanticTaskRepository(SEMANTIC_ROOT / "tasks").load(
        "statement-function-classification", "2.1.0"
    )

    assert task.canonical_task == "semantic-profile-classification"


def test_ontology_identity_is_independent_from_task_version() -> None:
    ontology = ResourceOntologyDefinitionRepository().load("applicability-functions", "1.1.0")

    assert ontology.dimension == "applicability_functions"
    assert "exception over exclusion" in ontology.semantics["tie_break_rules"][0]


def test_applicability_semantics_task_uses_narrow_ontology_version() -> None:
    task, _ = SemanticTaskRepository(SEMANTIC_ROOT / "tasks").load(
        "semantic-profile-classification", "2.4.0"
    )

    assert task.ontologies["applicability_functions"].version == "1.2.0"
    ontology = ResourceOntologyDefinitionRepository().load("applicability-functions", "1.2.0")
    exclusions = ontology.semantics["exclusions_from_dimension"]
    assert any("Prerequisites" in item for item in exclusions)
    assert any("Local if/when" in item for item in exclusions)
