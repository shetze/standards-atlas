"""Consistent formatting helpers for human-readable reports."""

from __future__ import annotations


def format_decimal(value: float | None, *, digits: int = 4, missing: str = "n/a") -> str:
    """Format an optional decimal value with a fixed number of digits."""
    return missing if value is None else f"{value:.{digits}f}"


def format_percentage(
    value: float | None,
    *,
    digits: int = 1,
    missing: str = "n/a",
) -> str:
    """Format an optional ratio as a percentage."""
    return missing if value is None else f"{value * 100:.{digits}f}%"


def format_seconds(value: float | None, *, digits: int = 2, missing: str = "n/a") -> str:
    """Format an optional duration in seconds."""
    return missing if value is None else f"{value:.{digits}f}s"


def format_gigabytes(value: float | None, *, digits: int = 2, missing: str = "n/a") -> str:
    """Format an optional memory value in gigabytes."""
    return missing if value is None else f"{value:.{digits}f}GB"
