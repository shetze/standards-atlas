from standards_atlas.application.semantic_classification import (
    ResourceSemanticProfileRepository,
)


def test_current_functional_safety_profile_is_versioned_resource() -> None:
    profile = ResourceSemanticProfileRepository().load("functional-safety", "1.0.0")

    assert profile.id == "functional-safety"
    assert profile.version == "1.0.0"
    assert profile.dimensions["statement_functions"].version == "2.0.0"
    assert profile.dimensions["knowledge_kinds"].version == "2.1.0"
    assert profile.dimensions["applicability_functions"].version == "1.2.0"
    assert profile.dimensions["role_relation_types"].version == "1.0.0"


def test_profile_can_expose_task_specific_dimension_view() -> None:
    profile = ResourceSemanticProfileRepository().load("functional-safety", "1.0.0")

    selected = profile.select_dimensions(("statement_functions", "knowledge_kinds"))

    assert selected.reference.as_text() == "functional-safety:1.0.0"
    assert tuple(selected.dimensions) == ("statement_functions", "knowledge_kinds")
