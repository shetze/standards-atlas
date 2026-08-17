"""Markdown export adapter for EngineeringDocument objects."""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping
from pathlib import Path

from standards_atlas.adapters.artifact_lineage import write_file_lineage_manifest
from standards_atlas.domain.model import (
    CodeBlock,
    DocumentStructure,
    EngineeringDocument,
    FormulaBlock,
    ListBlock,
    NoteBlock,
    PictureBlock,
    RelationScope,
    TableBlock,
    TextBlock,
)

_MAX_TOC_DEPTH = 4
_OMITTED_STRUCTURES = {DocumentStructure.FOREWORD, DocumentStructure.INTRODUCTION}


class MarkdownExporter:
    """Render one EngineeringDocument as a standalone Markdown file."""

    def export_document(
        self,
        document: EngineeringDocument,
        target: Path,
        *,
        link_targets: Mapping[tuple[str, str], str] | None = None,
    ) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        document = _materialize_visual_assets(document, target.parent)
        target.write_text(
            self.render(document, link_targets=link_targets),
            encoding="utf-8",
        )
        write_file_lineage_manifest(
            target,
            document,
            kind="markdown_export",
            media_type="text/markdown",
        )
        return target

    def render(
        self,
        document: EngineeringDocument,
        *,
        link_targets: Mapping[tuple[str, str], str] | None = None,
    ) -> str:
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
                rendered = _render_block(block, clause, document, link_targets=link_targets)
                if rendered:
                    lines.extend((rendered.rstrip(), ""))
        return "\n".join(lines).rstrip() + "\n"


def _exportable_clauses(document: EngineeringDocument):
    for clause in document.clauses:
        reference = clause.reference.clause.strip()
        if not reference or reference == "0":
            continue
        structure = clause.semantic_classification.document_structure
        if structure is not None and structure.category in _OMITTED_STRUCTURES:
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


def _render_block(
    block: object,
    clause: object,
    document: EngineeringDocument,
    *,
    link_targets: Mapping[tuple[str, str], str] | None = None,
) -> str:
    if isinstance(block, TextBlock):
        return _link_references(block.text, clause, document, link_targets=link_targets)
    if isinstance(block, ListBlock):
        return "\n".join(
            _render_list_item(
                item,
                block.ordered,
                index,
                clause=clause,
                document=document,
                link_targets=link_targets,
            )
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
        reference = block.image_path or block.embedded_data_uri
        return f"![{caption}]({reference})" if reference else f"*{caption}*"
    if isinstance(block, FormulaBlock):
        if block.extraction_status == "visual_only":
            page = block.source_evidence[0].page_number if block.source_evidence else None
            suffix = f" on page {page}" if page is not None else ""
            original = block.original_expression or block.expression
            detail = f" `{original}`" if original else ""
            status = f"*[Formula{suffix} — semantic transcription unavailable]*{detail}"
            reference = block.image_path or block.embedded_data_uri
            if reference:
                return f"![Formula{suffix}]({reference})\n\n{status}"
            return status
        if block.representation == "latex":
            return f"$$\n{block.expression}\n$$"
        return block.expression
    if isinstance(block, CodeBlock):
        return f"```{block.language or ''}\n{block.code}\n```"
    if isinstance(block, NoteBlock):
        body = "\n\n".join(
            filter(
                None,
                (
                    _render_block(item, clause, document, link_targets=link_targets)
                    for item in block.content
                ),
            )
        )
        title = block.note_kind or "Note"
        text = f"**{title}.**" + (f" {body}" if body else "")
        return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
    raise TypeError(f"Unsupported content block: {type(block)!r}")


def _render_list_item(
    item: object,
    ordered: bool,
    index: int,
    depth: int = 0,
    *,
    clause: object,
    document: EngineeringDocument,
    link_targets: Mapping[tuple[str, str], str] | None = None,
) -> str:
    marker = f"{index}." if ordered else "-"
    text = _link_references(item.text, clause, document, link_targets=link_targets)
    lines = [f"{'  ' * depth}{marker} {text}"]
    for child_index, child in enumerate(item.children, 1):
        lines.append(
            _render_list_item(
                child,
                child.ordered,
                child_index,
                depth + 1,
                clause=clause,
                document=document,
                link_targets=link_targets,
            )
        )
    return "\n".join(lines)


def _link_references(
    text: str,
    clause: object,
    document: EngineeringDocument,
    *,
    link_targets: Mapping[tuple[str, str], str] | None = None,
) -> str:
    """Render resolved internal and cross-document relations as Markdown links."""
    internal_targets = {item.reference.clause for item in document.clauses}
    relations = clause.semantic_classification.relations
    for relation in sorted(
        relations,
        key=lambda item: len(item.display_text or item.target_reference),
        reverse=True,
    ):
        label = relation.display_text or relation.target_reference
        destination: str | None = None
        if relation.scope is RelationScope.INTERNAL:
            target = relation.target_reference.strip()
            if target in internal_targets:
                destination = f"#{_anchor(target)}"
            elif relation.target_clause_id and link_targets is not None:
                destination = link_targets.get((document.key.value, relation.target_clause_id))
        elif (
            relation.target_document_key and relation.target_clause_id and link_targets is not None
        ):
            destination = link_targets.get(
                (relation.target_document_key, relation.target_clause_id)
            )
        if not destination:
            continue
        pattern = re.compile(rf"(?<![\w.#-]){re.escape(label)}(?![\w-]|[.]\d)")
        text = pattern.sub(f"[{label}]({destination})", text)
    return text


def _materialize_visual_assets(
    document: EngineeringDocument,
    target_directory: Path,
) -> EngineeringDocument:
    """Write embedded visual payloads beside Markdown and rewrite their references."""
    assets_directory = target_directory / "assets"
    changed = False
    clauses = []
    for clause in document.clauses:
        content = []
        clause_changed = False
        for block in clause.content:
            if (
                not isinstance(block, (PictureBlock, FormulaBlock))
                or not block.embedded_data_uri
                or not block.content_hash
            ):
                content.append(block)
                continue
            decoded = _decode_data_uri(block.embedded_data_uri)
            if decoded is None:
                content.append(block)
                continue
            media_type, payload = decoded
            extension = _media_extension(media_type)
            assets_directory.mkdir(parents=True, exist_ok=True)
            asset_path = assets_directory / f"{block.content_hash}{extension}"
            if not asset_path.exists() or asset_path.read_bytes() != payload:
                asset_path.write_bytes(payload)
            content.append(block.model_copy(update={"image_path": f"assets/{asset_path.name}"}))
            clause_changed = True
        clauses.append(
            clause.model_copy(update={"content": tuple(content)}) if clause_changed else clause
        )
        changed = changed or clause_changed
    return document.model_copy(update={"clauses": tuple(clauses)}) if changed else document


def _decode_data_uri(uri: str) -> tuple[str, bytes] | None:
    if not uri.startswith("data:") or ";base64," not in uri:
        return None
    header, encoded = uri.split(",", 1)
    media_type = header[5:].split(";", 1)[0]
    try:
        return media_type, base64.b64decode(encoded, validate=True)
    except ValueError:
        return None


def _media_extension(media_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
    }.get(media_type, ".bin")
