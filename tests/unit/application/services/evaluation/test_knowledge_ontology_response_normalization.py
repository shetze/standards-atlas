from standards_atlas.application.semantic_qualification.proposals import (
    _normalize_selection_payload,
)


def test_missing_ontology_dimensions_are_normalized_to_abstentions() -> None:
    normalized = _normalize_selection_payload(
        {
            "statement_functions": ["description"],
            "primary_function": "description",
            "confidence": 0.8,
            "rationale": "Descriptive clause.",
        },
        required_fields=[
            "knowledge_kinds",
            "primary_knowledge_kind",
            "process_functions",
            "primary_process_function",
            "applicability_functions",
            "primary_applicability_function",
            "role_relation_types",
            "primary_role_relation_type",
        ],
    )

    assert normalized["knowledge_kinds"] == []
    assert normalized["primary_knowledge_kind"] is None
    assert normalized["process_functions"] == []
    assert normalized["primary_process_function"] is None
    assert normalized["applicability_functions"] == []
    assert normalized["primary_applicability_function"] is None
    assert normalized["role_relation_types"] == []
    assert normalized["primary_role_relation_type"] is None


def test_v1_payload_is_not_extended_with_v2_fields() -> None:
    normalized = _normalize_selection_payload(
        {
            "statement_functions": ["description"],
            "primary_function": "description",
        },
        required_fields=["statement_functions", "primary_function"],
    )

    assert "knowledge_kinds" not in normalized
