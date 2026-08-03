from standards_atlas.application.semantic_qualification.adaptive_interview import (
    AdaptiveInterviewPlanner,
    InterviewDimension,
)


def test_planner_uses_normalized_scope_information() -> None:
    plan = AdaptiveInterviewPlanner().plan(
        {
            "content": {"text": "This part applies to software components."},
            "context": {
                "clause_type": "scope",
                "canonical_section": "scope",
                "structural_roles": [],
            },
        }
    )

    dimensions = {question.dimension for question in plan.questions}
    assert InterviewDimension.APPLICABILITY in dimensions
    assert InterviewDimension.RESPONSIBILITY not in dimensions


def test_planner_prioritizes_detected_reference_semantics() -> None:
    plan = AdaptiveInterviewPlanner().plan(
        {
            "content": {"text": "The validation shall use the method in 8.4.2."},
            "context": {
                "clause_type": "requirement",
                "relations": [{"target_reference": "8.4.2"}],
            },
        }
    )

    questions = {question.id: question for question in plan.questions}
    assert "reference-semantics" in questions
    assert "validation_method" in questions["reference-semantics"].allowed_labels


def test_planner_skips_structurally_deterministic_statement_function() -> None:
    plan = AdaptiveInterviewPlanner().plan(
        {
            "content": {"text": "Example 1 — A possible implementation."},
            "context": {"structural_roles": ["example"]},
        }
    )

    assert InterviewDimension.STATEMENT_FUNCTION in plan.skipped_dimensions
    assert all(
        question.dimension is not InterviewDimension.STATEMENT_FUNCTION
        for question in plan.questions
    )
