"""Semantic-extraction-specific textual projections of clause content."""

from __future__ import annotations

from dataclasses import dataclass

from standards_atlas.domain.model.content import (
    ContentBlock,
    NoteBlock,
    TableBlock,
    render_block_as_plain_text,
)


@dataclass(frozen=True)
class SemanticTextProjection:
    """A clause text projection with table payload removed but context retained."""

    text: str
    source_character_count: int
    semantic_input_character_count: int
    omitted_table_block_count: int
    omitted_table_character_count: int


def project_clause_content(content: tuple[ContentBlock, ...]) -> SemanticTextProjection:
    """Render clause content for semantic extraction while omitting table cell payload."""
    source_parts = [render_block_as_plain_text(block).strip() for block in content]
    source_text = "\n\n".join(part for part in source_parts if part)
    rendered_parts: list[str] = []
    omitted_blocks = 0
    omitted_characters = 0

    for block in content:
        rendered, block_count, character_count = _project_block(block)
        if rendered.strip():
            rendered_parts.append(rendered.strip())
        omitted_blocks += block_count
        omitted_characters += character_count

    text = "\n\n".join(rendered_parts)
    return SemanticTextProjection(
        text=text,
        source_character_count=len(source_text),
        semantic_input_character_count=len(text),
        omitted_table_block_count=omitted_blocks,
        omitted_table_character_count=omitted_characters,
    )


def _project_block(block: ContentBlock) -> tuple[str, int, int]:
    if isinstance(block, TableBlock):
        original = render_block_as_plain_text(block)
        label = block.caption.strip() if block.caption else "table"
        return f"[Table omitted: {label}]", 1, len(original)

    if isinstance(block, NoteBlock):
        body_parts: list[str] = []
        block_count = 0
        character_count = 0
        for nested in block.content:
            rendered, nested_count, nested_characters = _project_block(nested)
            if rendered.strip():
                body_parts.append(rendered.strip())
            block_count += nested_count
            character_count += nested_characters
        body = "\n\n".join(body_parts)
        if block.note_kind and body:
            body = f"{block.note_kind}: {body}"
        elif block.note_kind:
            body = block.note_kind
        return body, block_count, character_count

    return render_block_as_plain_text(block), 0, 0
