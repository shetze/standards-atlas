"""Structured content blocks used by the canonical document model."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model.source_evidence import SourceEvidence


class ContentBlockBase(BaseModel):
    """Common metadata for ordered clause content."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    source_evidence: tuple[SourceEvidence, ...] = ()


class TextBlock(ContentBlockBase):
    """A prose paragraph or contiguous text fragment."""

    type: Literal["text"] = "text"
    text: str


class ListItem(BaseModel):
    """One potentially nested list item."""

    model_config = ConfigDict(frozen=True)

    text: str
    children: tuple[ListItem, ...] = ()


class ListBlock(ContentBlockBase):
    """An ordered or unordered list."""

    type: Literal["list"] = "list"
    ordered: bool = False
    items: tuple[ListItem, ...]


class TableCell(BaseModel):
    """One logical table cell."""

    model_config = ConfigDict(frozen=True)

    text: str
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    is_header: bool = False


class TableRow(BaseModel):
    """One logical table row."""

    model_config = ConfigDict(frozen=True)

    cells: tuple[TableCell, ...]


class TableBlock(ContentBlockBase):
    """A table with row and cell spanning information."""

    type: Literal["table"] = "table"
    rows: tuple[TableRow, ...]
    caption: str | None = None


class PictureBlock(ContentBlockBase):
    """A picture or diagram referenced from private workspace storage."""

    type: Literal["picture"] = "picture"
    caption: str | None = None
    image_path: str | None = None
    description: str | None = None


class FormulaBlock(ContentBlockBase):
    """A mathematical or engineering formula."""

    type: Literal["formula"] = "formula"
    expression: str
    representation: Literal["latex", "mathml", "text"] = "text"


class NoteBlock(ContentBlockBase):
    """A semantically marked note containing nested content blocks."""

    type: Literal["note"] = "note"
    note_kind: str | None = None
    content: tuple[ContentBlock, ...] = ()


ContentBlock = Annotated[
    TextBlock | ListBlock | TableBlock | PictureBlock | FormulaBlock | NoteBlock,
    Field(discriminator="type"),
]


def render_content_as_plain_text(content: tuple[ContentBlock, ...]) -> str:
    """Render structured content to a stable plain-text representation."""
    return "\n\n".join(
        rendered for block in content if (rendered := render_block_as_plain_text(block).strip())
    )


def render_block_as_plain_text(block: ContentBlock) -> str:
    """Render one content block without adapter-specific formatting."""
    if isinstance(block, TextBlock):
        return block.text

    if isinstance(block, ListBlock):
        return "\n".join(
            _render_list_item(item, ordered=block.ordered, index=index)
            for index, item in enumerate(block.items, start=1)
        )

    if isinstance(block, TableBlock):
        table = "\n".join(" | ".join(cell.text for cell in row.cells) for row in block.rows)
        return "\n".join(part for part in (block.caption, table) if part)

    if isinstance(block, PictureBlock):
        return block.description or block.caption or ""

    if isinstance(block, FormulaBlock):
        return block.expression

    if isinstance(block, NoteBlock):
        body = render_content_as_plain_text(block.content)
        if block.note_kind and body:
            return f"{block.note_kind}: {body}"
        return body or block.note_kind or ""

    raise TypeError(f"Unsupported content block: {type(block)!r}")


def _render_list_item(item: ListItem, *, ordered: bool, index: int) -> str:
    marker = f"{index}." if ordered else "-"
    lines = [f"{marker} {item.text}"]

    for child_index, child in enumerate(item.children, start=1):
        child_text = _render_list_item(
            child,
            ordered=ordered,
            index=child_index,
        )
        lines.extend(f"  {line}" for line in child_text.splitlines())

    return "\n".join(lines)
