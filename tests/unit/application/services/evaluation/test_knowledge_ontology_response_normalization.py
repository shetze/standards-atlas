from standards_atlas.application.semantic_qualification.proposals import (
    _adaptive_interview_supports_schema,
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


def test_missing_complete_role_relation_block_is_normalized_to_abstention() -> None:
    normalized = _normalize_selection_payload(
        {
            "statement_functions": ["description"],
            "primary_function": "description",
        },
        required_fields=[
            "statement_functions",
            "primary_function",
            "role_relation_types",
            "primary_role_relation_type",
            "role_relations",
        ],
    )

    assert normalized["role_relation_types"] == []
    assert normalized["primary_role_relation_type"] is None
    assert normalized["role_relations"] == []


def test_missing_role_relations_are_normalized_for_explicit_abstention() -> None:
    normalized = _normalize_selection_payload(
        {
            "statement_functions": ["description"],
            "primary_function": "description",
            "role_relation_types": [],
            "primary_role_relation_type": None,
        },
        required_fields=[
            "role_relation_types",
            "primary_role_relation_type",
            "role_relations",
        ],
    )

    assert normalized["role_relations"] == []


def test_missing_role_relations_are_not_normalized_for_positive_classification() -> None:
    normalized = _normalize_selection_payload(
        {
            "statement_functions": ["requirement"],
            "primary_function": "requirement",
            "role_relation_types": ["verifies"],
            "primary_role_relation_type": "verifies",
        },
        required_fields=[
            "role_relation_types",
            "primary_role_relation_type",
            "role_relations",
        ],
    )

    assert "role_relations" not in normalized


def test_partial_role_relation_block_is_not_normalized() -> None:
    normalized = _normalize_selection_payload(
        {
            "statement_functions": ["description"],
            "primary_function": "description",
            "role_relation_types": [],
        },
        required_fields=[
            "role_relation_types",
            "primary_role_relation_type",
            "role_relations",
        ],
    )

    assert "role_relations" not in normalized


def test_adaptive_interview_is_disabled_for_structured_role_relation_schema() -> None:
    assert not _adaptive_interview_supports_schema(
        {"required": ["statement_functions", "role_relations"]}
    )


def test_adaptive_interview_remains_available_for_classification_only_schema() -> None:
    assert _adaptive_interview_supports_schema(
        {"required": ["statement_functions", "role_relation_types"]}
    )


def test_duplicate_set_like_labels_are_deduplicated_before_domain_validation() -> None:
    normalized = _normalize_selection_payload(
        {
            "statement_functions": ["requirement", "requirement"],
            "primary_function": "requirement",
            "knowledge_kinds": ["process", "process", "artifact"],
            "primary_knowledge_kind": "process",
            "process_functions": ["activity", "activity"],
            "primary_process_function": "activity",
            "applicability_functions": ["inclusion", "inclusion"],
            "primary_applicability_function": "inclusion",
        }
    )

    assert normalized["statement_functions"] == ["requirement"]
    assert normalized["knowledge_kinds"] == ["process", "artifact"]
    assert normalized["process_functions"] == ["activity"]
    assert normalized["applicability_functions"] == ["inclusion"]
