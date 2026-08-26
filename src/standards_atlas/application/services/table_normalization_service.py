"""Deterministic structural normalization for first-class document tables."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from standards_atlas.domain.model import (
    Clause,
    DocumentTable,
    EngineeringDocument,
    NormalizedTable,
    NormalizedTableCell,
    NormalizedTableColumn,
    NormalizedTableFootnote,
    NormalizedTableReference,
    NormalizedTableRow,
    NormalizedTableRowKind,
    NoteBlock,
    TableBlock,
)

_FOOTNOTE = re.compile(r"^\s*(?:(NOTE|NOTES?)\b\s*[:.-]?|([a-z])\)|([*†‡]))\s*(.*)$", re.I)
_UNIT = re.compile(
    r"(?:\[|\()\s*(%|s|ms|us|µs|ns|min|h|Hz|kHz|MHz|V|mV|A|mA|°C|K|FIT|1/h|years?)\s*(?:\]|\))",
    re.I,
)
_REFERENCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "table",
        re.compile(r"\bTable\s+[A-Z0-9]+(?:[.-][A-Z0-9]+)*\b", re.I),
    ),
    (
        "clause",
        re.compile(r"\b(?:Clause|see)\s+[A-Z]?\d+(?:\.\d+)*\b", re.I),
    ),
    (
        "standard",
        re.compile(r"\b(?:IEC|ISO|EN)\s*\d+(?:-\d+)*(?::\d{4})?\b", re.I),
    ),
)


class TableNormalizationService:
    """Create a lossless, semantics-free normalized table projection."""

    def normalize_document(self, document: EngineeringDocument) -> tuple[NormalizedTable, ...]:
        tables_by_block = {
            table.table_block_id: table
            for table in document.tables
            if table.table_block_id is not None
        }
        normalized: list[NormalizedTable] = []
        sequence = 0
        for clause in document.clauses:
            ordinal = 0
            for block in _iter_tables(clause):
                ordinal += 1
                structural = tables_by_block.get(block.id)
                normalized.append(
                    self.normalize_table(
                        document,
                        clause,
                        block,
                        structural=structural,
                        ordinal=ordinal,
                        sequence=sequence,
                    )
                )
                sequence += 1
        return tuple(normalized)

    def normalize_table(
        self,
        document: EngineeringDocument,
        clause: Clause,
        table: TableBlock,
        *,
        structural: DocumentTable | None = None,
        ordinal: int = 1,
        sequence: int = 0,
    ) -> NormalizedTable:
        """Normalize one protected table block without semantic interpretation."""
        anchors, grid, width = _place_cells(table)
        height = len(table.rows)
        header_row_count = _header_row_count(table)
        row_kinds = _row_kinds(table, anchors, width, header_row_count)
        rows = tuple(
            NormalizedTableRow(
                index=row_index,
                kind=row_kinds[row_index],
                cells=tuple(cell for cell in anchors if cell.row_index == row_index),
                header_path=_row_header_path(row_index, grid, width),
            )
            for row_index in range(height)
        )
        columns = tuple(
            _normalized_column(column_index, grid, header_row_count)
            for column_index in range(width)
        )
        footnotes = _footnotes(rows, width)
        references = _references(anchors)
        reference = (
            structural.reference
            if structural is not None
            else _fallback_reference(clause.reference.as_text(), ordinal)
        )
        title = structural.title if structural is not None else table.caption
        table_id = structural.id if structural is not None else None
        return NormalizedTable(
            id=_stable_normalized_table_id(document.key.value, block_id=table.id),
            document_table_id=table_id,
            document_key=document.key.value,
            reference=reference,
            title=title,
            parent_clause_id=clause.id.value,
            parent_clause_reference=clause.reference.as_text(),
            table_block_id=table.id,
            width=width,
            height=height,
            header_row_count=header_row_count,
            columns=columns,
            rows=rows,
            footnotes=footnotes,
            references=references,
            source_evidence=table.source_evidence,
        )


def _iter_tables(clause: Clause) -> Iterable[TableBlock]:
    yield from _iter_blocks(clause.content)


def _iter_blocks(content: tuple[object, ...]) -> Iterable[TableBlock]:
    for block in content:
        if isinstance(block, TableBlock):
            yield block
        elif isinstance(block, NoteBlock):
            yield from _iter_blocks(block.content)


def _place_cells(
    table: TableBlock,
) -> tuple[tuple[NormalizedTableCell, ...], dict[tuple[int, int], NormalizedTableCell], int]:
    anchors: list[NormalizedTableCell] = []
    grid: dict[tuple[int, int], NormalizedTableCell] = {}
    width = 0
    for row_index, row in enumerate(table.rows):
        column_index = 0
        for source in row.cells:
            while (row_index, column_index) in grid:
                column_index += 1
            cell = NormalizedTableCell(
                row_index=row_index,
                column_index=column_index,
                text=source.text,
                row_span=source.row_span,
                column_span=source.column_span,
                is_header=source.is_header,
            )
            anchors.append(cell)
            for covered_row in range(row_index, row_index + source.row_span):
                for covered_column in range(column_index, column_index + source.column_span):
                    if (covered_row, covered_column) in grid:
                        raise ValueError(
                            "table spans overlap at "
                            f"row {covered_row}, column {covered_column}: {table.id}"
                        )
                    grid[(covered_row, covered_column)] = cell
            column_index += source.column_span
            width = max(width, column_index)
    if grid:
        width = max(width, max(column for _, column in grid) + 1)
    return tuple(anchors), grid, width


def _header_row_count(table: TableBlock) -> int:
    count = 0
    for row in table.rows:
        if row.cells and all(cell.is_header for cell in row.cells):
            count += 1
        else:
            break
    return count


def _row_kinds(
    table: TableBlock,
    anchors: tuple[NormalizedTableCell, ...],
    width: int,
    header_row_count: int,
) -> tuple[NormalizedTableRowKind, ...]:
    kinds: list[NormalizedTableRowKind] = []
    for index in range(len(table.rows)):
        if index < header_row_count:
            kinds.append(NormalizedTableRowKind.HEADER)
            continue
        row_cells = tuple(cell for cell in anchors if cell.row_index == index)
        kinds.append(
            NormalizedTableRowKind.FOOTNOTE
            if _looks_like_footnote(row_cells, width)
            else NormalizedTableRowKind.DATA
        )
    return tuple(kinds)


def _looks_like_footnote(cells: tuple[NormalizedTableCell, ...], width: int) -> bool:
    if len(cells) != 1:
        return False
    cell = cells[0]
    if cell.column_span < max(1, width):
        return False
    return _FOOTNOTE.match(cell.text) is not None


def _row_header_path(
    row_index: int,
    grid: dict[tuple[int, int], NormalizedTableCell],
    width: int,
) -> tuple[str, ...]:
    values: list[str] = []
    for column_index in range(width):
        cell = grid.get((row_index, column_index))
        if cell is None or not cell.is_header:
            break
        text = _normalize_text(cell.text)
        if text and (not values or values[-1] != text):
            values.append(text)
    return tuple(values)


def _normalized_column(
    column_index: int,
    grid: dict[tuple[int, int], NormalizedTableCell],
    header_row_count: int,
) -> NormalizedTableColumn:
    path: list[str] = []
    for row_index in range(header_row_count):
        cell = grid.get((row_index, column_index))
        if cell is None:
            continue
        text = _normalize_text(cell.text)
        if text and (not path or path[-1] != text):
            path.append(text)
    label = " / ".join(path) or None
    unit = None
    for value in reversed(path):
        if match := _UNIT.search(value):
            unit = match.group(1)
            break
    return NormalizedTableColumn(
        index=column_index,
        header_path=tuple(path),
        label=label,
        unit=unit,
    )


def _footnotes(
    rows: tuple[NormalizedTableRow, ...],
    width: int,
) -> tuple[NormalizedTableFootnote, ...]:
    del width
    result: list[NormalizedTableFootnote] = []
    for row in rows:
        if row.kind is not NormalizedTableRowKind.FOOTNOTE or not row.cells:
            continue
        text = _normalize_text(row.cells[0].text)
        match = _FOOTNOTE.match(text)
        if match is None:
            continue
        marker = next((value for value in match.groups()[:3] if value), None)
        body = match.group(4).strip() or text
        result.append(NormalizedTableFootnote(marker=marker, text=body, row_index=row.index))
    return tuple(result)


def _references(
    cells: tuple[NormalizedTableCell, ...],
) -> tuple[NormalizedTableReference, ...]:
    found: list[NormalizedTableReference] = []
    seen: set[tuple[str, str, int, int]] = set()
    for cell in cells:
        for kind, pattern in _REFERENCE_PATTERNS:
            for match in pattern.finditer(cell.text):
                text = _normalize_text(match.group(0))
                key = (kind, text.casefold(), cell.row_index, cell.column_index)
                if key in seen:
                    continue
                seen.add(key)
                found.append(
                    NormalizedTableReference(
                        text=text,
                        kind=kind,
                        row_index=cell.row_index,
                        column_index=cell.column_index,
                    )
                )
    return tuple(found)


def _stable_normalized_table_id(document_key: str, *, block_id: str) -> str:
    digest = hashlib.sha256(f"{document_key}\x1f{block_id}".encode()).hexdigest()[:16]
    return f"normalized-table:{digest}"


def _fallback_reference(clause_reference: str, ordinal: int) -> str:
    return f"{clause_reference}:table:{ordinal}"


def _normalize_text(value: str) -> str:
    return " ".join(value.split())
