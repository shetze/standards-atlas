from pathlib import Path

from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.semantic_qualification.proposals import SemanticTaskRepository

RESOURCES = Path("src/standards_atlas/resources/semantic")


def test_role_semantics_presence_task_and_prompt_share_schema() -> None:
    task, schema = SemanticTaskRepository(RESOURCES / "tasks").load(
        "role-semantics-presence", "1.0.0"
    )
    prompt = PromptRepository(RESOURCES / "prompts").load("role-semantics-presence", "1.0.0")
    assert task.task == "role-semantics-presence"
    assert prompt.output_schema == schema
    assert "role_semantics_present" in schema["required"]


def test_role_relation_extraction_task_and_prompt_share_schema() -> None:
    task, schema = SemanticTaskRepository(RESOURCES / "tasks").load(
        "role-relation-extraction", "1.0.0"
    )
    prompt = PromptRepository(RESOURCES / "prompts").load("role-relation-extraction", "1.0.0")
    assert task.task == "role-relation-extraction"
    assert prompt.output_schema == schema
    assert tuple(task.role_relation_taxonomy) == ()
    relation = schema["properties"]["role_relations"]["items"]["properties"]
    assert "relation_class" in relation
    assert "enum" not in relation["relation_class"]
    assert "predicate" in relation
