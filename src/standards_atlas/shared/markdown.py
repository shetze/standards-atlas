"""Small Markdown rendering primitives shared by report implementations."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum


class ColumnAlignment(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


def escape_table_cell(value: object) -> str:
    """Render a value safely inside a Markdown table cell."""
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def markdown_row(values: Sequence[object]) -> str:
    """Render one Markdown table row."""
    return "| " + " | ".join(escape_table_cell(value) for value in values) + " |"


def markdown_separator(alignments: Sequence[ColumnAlignment]) -> str:
    """Render a Markdown table alignment separator."""
    markers = {
        ColumnAlignment.LEFT: "---",
        ColumnAlignment.CENTER: ":---:",
        ColumnAlignment.RIGHT: "---:",
    }
    return markdown_row([markers[alignment] for alignment in alignments])


def markdown_table(
    headers: Sequence[object],
    rows: Sequence[Sequence[object]],
    *,
    alignments: Sequence[ColumnAlignment] | None = None,
) -> str:
    """Render a complete Markdown table."""
    resolved = tuple(ColumnAlignment.LEFT for _ in headers) if alignments is None else alignments
    if len(resolved) != len(headers):
        raise ValueError("Markdown table alignments must match the number of headers.")
    if any(len(row) != len(headers) for row in rows):
        raise ValueError("Markdown table rows must match the number of headers.")
    lines = [markdown_row(headers), markdown_separator(resolved)]
    lines.extend(markdown_row(row) for row in rows)
    return "\n".join(lines)
