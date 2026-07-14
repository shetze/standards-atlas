"""Errors raised by extracted-document normalization."""

from __future__ import annotations


class NormalizationError(RuntimeError):
    """Base error for deterministic document normalization."""


class NormalizationDataLossError(NormalizationError):
    """Raised when extracted source items are not accounted for."""

    def __init__(
        self,
        *,
        missing_item_ids: tuple[str, ...] = (),
        duplicate_item_ids: tuple[str, ...] = (),
    ) -> None:
        details: list[str] = []
        if missing_item_ids:
            details.append(f"missing: {', '.join(missing_item_ids)}")
        if duplicate_item_ids:
            details.append(f"duplicated: {', '.join(duplicate_item_ids)}")
        message = "Normalization source-item accounting failed"
        if details:
            message += f" ({'; '.join(details)})"
        super().__init__(message)
        self.missing_item_ids = missing_item_ids
        self.duplicate_item_ids = duplicate_item_ids
