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
    assert set(relation) == {"actor", "relation_class", "target"}


def test_role_prompts_define_actor_and_target_boundaries() -> None:
    extraction = PromptRepository(RESOURCES / "prompts").load("role-relation-extraction", "1.0.0")
    presence = PromptRepository(RESOURCES / "prompts").load("role-semantics-presence", "1.0.0")

    extraction_system = extraction.system_prompt
    assert "grammatical subject is not automatically an actor" in extraction_system
    assert "technical objects are not actors" in extraction_system
    assert "Do not repeat the actor as target" in extraction_system
    assert "responsibility" in extraction_system
    assert "The system shall satisfy the requirements" in extraction_system

    presence_system = presence.system_prompt
    assert "Being the grammatical subject is not sufficient" in presence_system
    assert "A hazard analysis shall be performed" in presence_system
    assert "The system shall satisfy the requirements" in presence_system


def test_v6_qualification_prompts_use_compact_four_dimension_contract() -> None:
    for prompt_id in (
        "content-only-v6",
        "structure-aware-v6",
        "evidence-first-v6",
        "bounded-reasoning-v6",
    ):
        prompt = PromptRepository(RESOURCES / "prompts").load(
            "statement-function-classification", prompt_id
        )
        system = prompt.system_prompt
        assert "four independent semantic dimensions" in system
        assert "4. role_semantics:" in system
        assert "5. role_relations" not in system
        assert "process-model functions" in system
        assert "process-model roles" not in system
        assert "Each role relation contains only actor, relation_class, and target" in system
        assert system.index("Role qualification rules:") < system.index("Return exactly one JSON")
        assert system.rstrip().endswith(
            "Confidence values must be JSON numbers from 0.0 through 1.0."
        )


def test_v8_applicability_qualification_prompt_is_binary_and_presence_first() -> None:
    prompt = PromptRepository(RESOURCES / "prompts").load(
        "statement-function-classification", "structure-aware-v8"
    )
    system = prompt.system_prompt
    applicability_items = prompt.output_schema["properties"]["applicability_functions"]["items"]
    primary = prompt.output_schema["properties"]["primary_applicability_function"]

    assert "Decide applicability_present first" in system
    assert "binary polarity" in system
    assert "Do not classify exception or applicability_condition" in system
    assert applicability_items["enum"] == ["inclusion", "exclusion"]
    assert primary["enum"] == ["inclusion", "exclusion", None]


def test_v9_applicability_prompts_encode_core_question_and_method_boundary() -> None:
    plain = PromptRepository(RESOURCES / "prompts").load(
        "statement-function-classification", "structure-aware-v9"
    )
    examples = PromptRepository(RESOURCES / "prompts").load(
        "statement-function-classification", "structure-aware-v9-examples"
    )

    core_question = (
        "Does the text contain a statement that restricts or extends the applicability "
        "of this clause or of a referenced clause?"
    )
    for prompt in (plain, examples):
        system = prompt.system_prompt
        assert core_question in system
        assert "technique, method, or measure applies or can be used" in system
        assert 'A bare qualifier such as "if applicable" does not decide applicability' in system
        assert "contains applicability statements in both directions" in system
        assert prompt.output_schema["properties"]["applicability_functions"]["items"]["enum"] == [
            "inclusion",
            "exclusion",
        ]

    assert "Applicability boundary examples:" not in plain.system_prompt
    assert examples.system_prompt.count("- Positive:") == 1
    assert examples.system_prompt.count("- Negative:") == 1
    assert "applicability_present=true" in examples.system_prompt
    assert "applicability_present=false" in examples.system_prompt


def test_v10_applicability_prompt_uses_only_the_presence_question() -> None:
    task, schema = SemanticTaskRepository(RESOURCES / "tasks").load(
        "semantic-profile-classification", "2.5.0"
    )
    prompt = PromptRepository(RESOURCES / "prompts").load(
        "semantic-profile-classification", "structure-aware-v10"
    )

    core_question = (
        "Does the text contain statements that restrict or extend the applicability "
        "of this clause or a referenced clause?"
    )
    system = prompt.system_prompt
    lowered = system.lower()
    applicability_fields = {
        field
        for field in prompt.output_schema["properties"]
        if field.startswith("applicability") or field.startswith("primary_applicability")
    }

    assert prompt.output_schema == schema
    assert task.version == "2.5.0"
    assert system.count(core_question) == 1
    assert "Record the answer in applicability_present." in system
    assert applicability_fields == {"applicability_present"}
    assert "applicability_present" in prompt.output_schema["required"]
    for attention_cue in (
        "polarity",
        "inclusion",
        "exclusion",
        "exception",
        "subtype",
        "applicability_functions",
        "primary_applicability_function",
        " negative ",
        " false",
        " not ",
        "never",
    ):
        assert attention_cue not in lowered
