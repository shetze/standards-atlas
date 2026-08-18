from standards_atlas.application.semantic_qualification.batch import (
    ProposalBatchExecutor,
    ProposalItemOutcome,
)


def test_batch_executor_aggregates_item_outcomes() -> None:
    seen: list[tuple[int, int, str]] = []

    def handle(current: int, total: int, item: str) -> ProposalItemOutcome:
        seen.append((current, total, item))
        if item == "bad":
            return ProposalItemOutcome(False, "bad: failed")
        return ProposalItemOutcome(
            True,
            fresh_predictions=1,
            fresh_inference_duration_seconds=0.25,
        )

    outcome = ProposalBatchExecutor[str]().execute(("good", "bad"), handle)

    assert seen == [(1, 2, "good"), (2, 2, "bad")]
    assert outcome.generated == 1
    assert outcome.failed == 1
    assert outcome.errors == ("bad: failed",)
    assert outcome.fresh_predictions == 1
    assert outcome.cached_predictions == 0
    assert outcome.fresh_inference_duration_seconds == 0.25
