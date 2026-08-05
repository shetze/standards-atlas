from __future__ import annotations

import pytest

from standards_atlas.shared.markdown import (
    ColumnAlignment,
    escape_table_cell,
    markdown_row,
    markdown_table,
)


def test_markdown_table_renders_alignment_and_escapes_cells() -> None:
    rendered = markdown_table(
        ("Name", "Value"),
        (("a|b", 1), ("line\nbreak", 2)),
        alignments=(ColumnAlignment.LEFT, ColumnAlignment.RIGHT),
    )

    assert rendered == ("| Name | Value |\n| --- | ---: |\n| a\\|b | 1 |\n| line<br>break | 2 |")
    assert escape_table_cell("a\\b") == "a\\\\b"
    assert markdown_row(("a", "b")) == "| a | b |"


def test_markdown_table_rejects_inconsistent_shapes() -> None:
    with pytest.raises(ValueError, match="alignments"):
        markdown_table(("a",), (), alignments=())
    with pytest.raises(ValueError, match="rows"):
        markdown_table(("a",), (("a", "b"),))
