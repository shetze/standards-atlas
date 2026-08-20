from pathlib import Path

import pytest

from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.semantic_qualification.dimensions import qualification_dimension
from standards_atlas.application.semantic_qualification.proposals import (
    SemanticTaskRepository,
    _selection_payload_for_annotation,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)

SEMANTIC_ROOT = Path("src/standards_atlas/resources/semantic")


@pytest.mark.parametrize(
    ("task", "version", "dimension"),
    [
        ("statement-function-classification", "3.0.0", "statement_functions"),
        ("knowledge-kind-classification", "1.0.0", "knowledge_kinds"),
        ("process-function-classification", "1.0.0", "process_functions"),
        ("applicability-extraction", "1.0.0", "applicability_functions"),
        ("role-relation-extraction", "1.0.0", "role_relation_types"),
    ],
)
def test_split_tasks_load_independently(task: str, version: str, dimension: str) -> None:
    definition, schema = SemanticTaskRepository(SEMANTIC_ROOT / "tasks").load(task, version)

    assert definition.task == task
    assert qualification_dimension(task).name == dimension
    assert schema["additionalProperties"] is False
    assert "confidence" in schema["required"]
    assert "rationale" in schema["required"]


@pytest.mark.parametrize(
    "task",
    [
        "statement-function-classification",
        "knowledge-kind-classification",
        "process-function-classification",
        "applicability-extraction",
        "role-relation-extraction",
    ],
)
def test_split_tasks_have_four_focused_prompt_variants(task: str) -> None:
    repository = PromptRepository(SEMANTIC_ROOT / "prompts")
    for version in (
        "content-only-v1",
        "structure-aware-v1",
        "evidence-first-v1",
        "bounded-reasoning-v1",
    ):
        prompt = repository.load(task, version)
        assert prompt.task == task
        assert prompt.output_schema["additionalProperties"] is False


def test_role_relation_types_are_derived_from_structured_relations() -> None:
    payload = _selection_payload_for_annotation(
        {
            "role_relations": [
                {
                    "role": "Verifier",
                    "relation": "verifies",
                    "target": "software requirements",
                    "condition": None,
                    "evidence": "The verifier shall verify the software requirements.",
                    "confidence": 0.96,
                },
                {
                    "role": "Verifier",
                    "relation": "independent_of",
                    "target": "the activity being verified",
                    "condition": None,
                    "evidence": "The verifier shall be independent of the activity.",
                    "confidence": 0.93,
                },
            ],
            "confidence": 0.93,
            "rationale": "explicit role relations",
        },
        task="role-relation-extraction",
    )

    assert payload["role_relation_types"] == ["verifies", "independent_of"]
    assert payload["primary_role_relation_type"] == "verifies"


@pytest.mark.parametrize(
    "manifest_name",
    [
        "multidimensional-semantic-qualification-v4-statement-function-v1.yaml",
        "multidimensional-semantic-qualification-v4-knowledge-kind-v1.yaml",
        "multidimensional-semantic-qualification-v4-process-function-v1.yaml",
        "multidimensional-semantic-qualification-v4-applicability-v1.yaml",
        "multidimensional-semantic-qualification-v4-role-relation-v1.yaml",
    ],
)
def test_split_qualification_manifests_are_routing_enabled(manifest_name: str) -> None:
    manifest = QualificationMatrixManifest.load(Path("manifests") / manifest_name)

    assert manifest.schema_version == "1.6"
    assert manifest.routing is not None
    assert manifest.routing.contract_version == "1.1.0"
    assert manifest.execution.mode == "full_matrix"
    assert not manifest.consensus.enabled


def test_role_relation_extraction_metrics_score_grounded_relation_tuple() -> None:
    from standards_atlas.application.semantic_qualification.annotations import (
        StatementFunctionSelection,
    )
    from standards_atlas.application.semantic_qualification.qualification import (
        _role_relation_extraction_metrics,
    )
    from standards_atlas.domain.model import RoleRelation

    expected = StatementFunctionSelection(
        role_relations=(
            RoleRelation(
                role="Verifier",
                relation="verifies",
                target="Software requirements",
                evidence="Verifier verifies software requirements",
                confidence=0.9,
            ),
        )
    )
    predicted = StatementFunctionSelection(
        role_relations=(
            RoleRelation(
                role=" verifier ",
                relation="verifies",
                target="software   requirements",
                evidence="different evidence wording is not part of semantic matching",
                confidence=0.8,
            ),
        )
    )

    metrics = _role_relation_extraction_metrics([(predicted, expected)])

    assert metrics.exact_match_rate == 1.0
    assert metrics.f1 == 1.0
