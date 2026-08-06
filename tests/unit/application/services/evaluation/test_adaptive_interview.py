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


def test_scope_context_does_not_offer_scope_definition_as_applicability() -> None:
    plan = AdaptiveInterviewPlanner().plan(
        {
            "content": {"text": "This part applies to software components."},
            "context": {
                "clause_type": "scope",
                "canonical_section": "scope",
            },
        }
    )

    presence = next(
        question for question in plan.questions if question.id == "applicability-presence"
    )
    from standards_atlas.application.semantic_qualification.adaptive_interview import (
        follow_up_question,
    )

    subtype = follow_up_question(presence)
    assert subtype is not None
    assert "scope_definition" not in subtype.allowed_labels
    assert set(subtype.allowed_labels) == {
        "applicability_condition",
        "inclusion",
        "exclusion",
        "exception",
        "none",
    }


def test_planner_adds_process_question_for_process_signals() -> None:
    plan = AdaptiveInterviewPlanner().plan(
        {
            "content": {"text": "Before verification, the safety plan shall be available."},
            "context": {"clause_type": "requirement"},
        }
    )

    question = next(
        item for item in plan.questions if item.dimension is InterviewDimension.PROCESS_FUNCTION
    )
    assert "prerequisite" in question.allowed_labels
    assert "sequence" in question.allowed_labels


def test_planner_offers_warning_as_statement_function() -> None:
    plan = AdaptiveInterviewPlanner().plan(
        {
            "content": {"text": "However, an unsuitable model can produce unreliable results."},
            "context": {"clause_type": "paragraph"},
        }
    )

    question = next(
        item for item in plan.questions if item.dimension is InterviewDimension.STATEMENT_FUNCTION
    )
    assert "warning" in question.allowed_labels


def test_statement_function_question_uses_current_taxonomy() -> None:
    plan = AdaptiveInterviewPlanner().plan(
        {
            "content": {"text": "The overview should not be regarded as exhaustive."},
            "context": {"clause_type": "paragraph"},
        }
    )

    question = next(
        item for item in plan.questions if item.dimension is InterviewDimension.STATEMENT_FUNCTION
    )
    assert "condemnation" in question.allowed_labels
    assert "guideline" not in question.allowed_labels
    assert "statement functions" in question.question.lower()
