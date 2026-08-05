"""Progress events and reporting port for semantic proposal execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProposalProgress:
    """Progress event emitted while generating semantic proposals."""

    current: int
    total: int
    example_id: str
    status: str
    document_key: str
    reference: str | None
    title: str | None
    detail: str | None = None
    elapsed_seconds: float | None = None
    attempt: int | None = None
    max_attempts: int | None = None


class ProposalProgressReporter(Protocol):
    """Application port receiving proposal progress events."""

    def __call__(self, progress: ProposalProgress) -> None:
        """Report one proposal progress event."""
        ...
