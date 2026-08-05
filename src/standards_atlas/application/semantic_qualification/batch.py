"""Batch execution primitives for resumable semantic proposal runs."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ProposalItemOutcome:
    """Result of processing one proposal candidate."""

    generated: bool
    error: str | None = None


@dataclass(frozen=True)
class ProposalBatchOutcome:
    """Aggregate result of one proposal batch."""

    generated: int
    failed: int
    errors: tuple[str, ...]


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
        total = len(items)
        for current, item in enumerate(items, start=1):
            outcome = handler(current, total, item)
            if outcome.generated:
                generated += 1
            else:
                failed += 1
                if outcome.error is not None:
                    errors.append(outcome.error)
        return ProposalBatchOutcome(generated, failed, tuple(errors))
