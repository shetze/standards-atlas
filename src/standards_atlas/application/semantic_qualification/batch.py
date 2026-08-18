"""Batch execution primitives for resumable semantic proposal runs."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ProposalItemOutcome:
    """Result of processing one proposal candidate."""

    generated: bool
    error: str | None = None
    fresh_predictions: int = 0
    cached_predictions: int = 0
    fresh_inference_duration_seconds: float = 0.0


@dataclass(frozen=True)
class ProposalBatchOutcome:
    """Aggregate result of one proposal batch."""

    generated: int
    failed: int
    errors: tuple[str, ...]
    fresh_predictions: int
    cached_predictions: int
    fresh_inference_duration_seconds: float


class ProposalBatchExecutor[T]:
    """Execute proposal candidates sequentially and aggregate their outcomes."""

    def execute(
        self,
        items: Sequence[T],
        handler: Callable[[int, int, T], ProposalItemOutcome],
    ) -> ProposalBatchOutcome:
        generated = 0
        failed = 0
        errors: list[str] = []
        fresh_predictions = 0
        cached_predictions = 0
        fresh_inference_duration_seconds = 0.0
        total = len(items)
        for current, item in enumerate(items, start=1):
            outcome = handler(current, total, item)
            if outcome.generated:
                generated += 1
                fresh_predictions += outcome.fresh_predictions
                cached_predictions += outcome.cached_predictions
                fresh_inference_duration_seconds += outcome.fresh_inference_duration_seconds
            else:
                failed += 1
                if outcome.error is not None:
                    errors.append(outcome.error)
        return ProposalBatchOutcome(
            generated,
            failed,
            tuple(errors),
            fresh_predictions,
            cached_predictions,
            fresh_inference_duration_seconds,
        )
