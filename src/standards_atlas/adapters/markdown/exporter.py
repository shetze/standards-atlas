"""Markdown export adapter for EngineeringDocument objects."""

from __future__ import annotations

import re
from pathlib import Path

from standards_atlas.domain.model import (
    CodeBlock,
    EngineeringDocument,
    FormulaBlock,
    ListBlock,
    NoteBlock,
    PictureBlock,
    SemanticRole,
    TableBlock,
    TextBlock,
)

_MAX_TOC_DEPTH = 4
_OMITTED_ROLES = {SemanticRole.FOREWORD, SemanticRole.INTRODUCTION}


class MarkdownExporter:
    """Render one EngineeringDocument as a standalone Markdown file."""

    def export_document(self, document: EngineeringDocument, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render(document), encoding="utf-8")
        return target

    def render(self, document: EngineeringDocument) -> str:
        clauses = tuple(sorted(_exportable_clauses(document), key=_clause_sort_key))
        lines = [f"# {document.title}", ""]
        toc = _render_toc(clauses)
        if toc:
            lines.extend(("## Contents", "", toc, ""))
        for clause in clauses:
            reference = clause.reference.clause.strip()
            heading = " ".join(part for part in (reference, clause.title) if part).strip()
            if not heading:
                continue
            lines.extend(
                (
                    f'<a id="{_anchor(reference)}"></a>',
                    f"{'#' * _heading_level(reference)} {heading}",
                    "",
                )
            )
            for block in clause.content:
                rendered = _render_block(block)
                if rendered:
                    lines.extend((rendered.rstrip(), ""))
        return "\n".join(lines).rstrip() + "\n"


def _exportable_clauses(document: EngineeringDocument):
    for clause in document.clauses:
        reference = clause.reference.clause.strip()
        if not reference or reference == "0":
            continue
        if _OMITTED_ROLES.intersection(clause.semantic_roles):
            continue
        yield clause


def _render_toc(clauses: tuple[object, ...]) -> str:
    lines: list[str] = []
    for clause in clauses:
        reference = clause.reference.clause.strip()
        depth = _reference_depth(reference)
        if depth > _MAX_TOC_DEPTH:
            continue
        label = " ".join(part for part in (reference, clause.title) if part).strip()
        indent = "  " * (depth - 1)
        lines.append(f"{indent}- [{label}](#{_anchor(reference)})")
    return "\n".join(lines)


def _heading_level(reference: str) -> int:
    return min(_reference_depth(reference) + 1, 6)


def _reference_depth(reference: str) -> int:
    reference = reference.strip()
    return reference.count(".") + 1


def _clause_sort_key(clause: object) -> tuple[object, ...]:
    return _reference_sort_key(clause.reference.clause)


def _reference_sort_key(reference: str) -> tuple[object, ...]:
    parts = reference.strip().split(".")
    first = parts[0]
    if first.isdigit():
        category = 0
    elif re.fullmatch(r"[A-Z]+", first):
        category = 1
    else:
        category = 2
    normalized: list[tuple[int, object]] = []
    for part in parts:
        if part.isdigit():
            normalized.append((0, int(part)))
        else:
            normalized.append((1, part.casefold()))
    return (category, *normalized)


def _anchor(reference: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", reference.casefold()).strip("-")
    return f"clause-{normalized}"


def _render_block(block: object) -> str:
    if isinstance(block, TextBlock):
        return block.text
    if isinstance(block, ListBlock):
        return "\n".join(
            _render_list_item(item, block.ordered, index)
            for index, item in enumerate(block.items, 1)
        )
    if isinstance(block, TableBlock):
        rows = [[cell.text.replace("|", "\\|") for cell in row.cells] for row in block.rows]
        if not rows:
            return block.caption or ""
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        header = rows[0]
        body = rows[1:]
        table = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
        table.extend("| " + " | ".join(row) + " |" for row in body)
        return "\n\n".join(part for part in (block.caption, "\n".join(table)) if part)
    if isinstance(block, PictureBlock):
        caption = block.caption or block.description or "Figure"
        return f"![{caption}]({block.image_path})" if block.image_path else f"*{caption}*"
    if isinstance(block, FormulaBlock):
        if block.representation == "latex":
            return f"$$\n{block.expression}\n$$"
        return block.expression
    if isinstance(block, CodeBlock):
        return f"```{block.language or ''}\n{block.code}\n```"
    if isinstance(block, NoteBlock):
        body = "\n\n".join(filter(None, (_render_block(item) for item in block.content)))
        title = block.note_kind or "Note"
        text = f"**{title}.**" + (f" {body}" if body else "")
        return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
    raise TypeError(f"Unsupported content block: {type(block)!r}")


def _render_list_item(item: object, ordered: bool, index: int, depth: int = 0) -> str:
    marker = f"{index}." if ordered else "-"
    lines = [f"{'  ' * depth}{marker} {item.text}"]
    for child_index, child in enumerate(item.children, 1):
        lines.append(_render_list_item(child, ordered, child_index, depth + 1))
    return "\n".join(lines)
