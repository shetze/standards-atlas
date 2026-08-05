from pathlib import Path

from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseContentProfile,
)
from standards_atlas.application.semantic_qualification.eligibility import (
    SemanticTaskEligibilityPolicy,
    eligibility_from_input,
)
from standards_atlas.application.semantic_qualification.proposals import (
    SemanticTaskRepository,
)


def test_statement_function_task_excludes_table_dominant_content() -> None:
    task, _ = SemanticTaskRepository(
        Path("src/standards_atlas/resources/semantic/tasks")
    ).load("statement-function-classification", "2.0.0")

    result = SemanticTaskEligibilityPolicy.from_task(task).evaluate(
        item_kind="clause",
        content_profile=ClauseContentProfile.TABLE_DOMINANT,
    )

    assert result.model_dump(mode="json") == {
        "eligible": False,
        "item_kind": "clause",
        "content_profile": "table_dominant",
        "reason": "table_dominant",
        "alternative_task": "structured-table-interpretation",
    }


def test_mixed_text_clause_remains_eligible() -> None:
    task, _ = SemanticTaskRepository(
        Path("src/standards_atlas/resources/semantic/tasks")
    ).load("statement-function-classification", "2.0.0")

    result = eligibility_from_input(
        SemanticTaskEligibilityPolicy.from_task(task),
        {
            "context": {
                "content_profile": "text_dominant",
                "table_block_count": 1,
            }
        },
    )

    assert result.eligible is True
    assert result.reason is None
