"""Parse Atlas data files into structured Python objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from standards_atlas.adapters.atlasdata.metadata import AtlasMetadata, parse_metadata
from standards_atlas.adapters.atlasdata.structure_expander import (
    StructureItem,
    expand_structure_line,
)


@dataclass(frozen=True)
class InitializationRecord:
    """One public initialization record, independent of serialized field order.

    ``content`` holds public text (the caption for TABLE); ``type_marker``
    holds a type marker, or the parent clause reference for TABLE. Only TABLE
    serializes these semantic values in reverse order: parent, then caption.
    """

    kind: str
    hash_value: str
    reference: str
    content: str
    type_marker: str
    semantic_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class AtlasStandardData:
    """Parsed representation of one Atlas standard data file."""

    metadata: AtlasMetadata
    structure_items: list[StructureItem]
    initialization_records: list[InitializationRecord]


_STRUCTURE_BLOCK_PATTERN = re.compile(
    r"structure=\(\s*(?P<body>.*?)\s*\)",
    re.DOTALL,
)

_DATA_MARKER = "#---data---#"
_TABLE_LAYOUT_PREFIX = "# table-record-layout:"
TABLE_RECORD_LAYOUT = f"{_TABLE_LAYOUT_PREFIX} parent-caption"
_TABLE_PARENT_REFERENCE = re.compile(r"(?:[0-9]+|[A-Za-z])(?:\.[A-Za-z0-9]+)*")

_INITIALIZATION_RECORD_KINDS = {
    "TOC",
    "PublicTXT",
    "LocalTXT",
    "TEXT",
    "TABLE",
    "TABLEINDEX",
}


def parse_standard_file(path: Path) -> AtlasStandardData:
    """Parse an Atlas standard data file."""
    return parse_standard_text(path.read_text(encoding="utf-8"))


def parse_standard_text(text: str) -> AtlasStandardData:
    """Parse Atlas standard data file content."""
    metadata = parse_metadata(text)
    structure_lines = parse_structure_block(text)

    structure_items: list[StructureItem] = []
    for line in structure_lines:
        structure_items.extend(expand_structure_line(line))

    initialization_records = parse_initialization_records(text)

    return AtlasStandardData(
        metadata=metadata,
        structure_items=structure_items,
        initialization_records=initialization_records,
    )


def parse_structure_block(text: str) -> list[str]:
    """Extract quoted structure lines from the structure block."""
    match = _STRUCTURE_BLOCK_PATTERN.search(text)

    if match is None:
        raise ValueError("Missing structure block.")

    body = match.group("body")
    lines: list[str] = []

    for raw_line in body.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if not _is_quoted(line):
            raise ValueError(f"Invalid structure line. Expected quoted string, got: {line!r}")

        lines.append(line[1:-1])

    return lines


def parse_initialization_records(text: str) -> list[InitializationRecord]:
    """Parse initialization records, accepting both TABLE column layouts."""
    if _DATA_MARKER not in text:
        return []

    _, data_section = text.split(_DATA_MARKER, 1)
    table_layout = _table_record_layout(data_section)

    records: list[InitializationRecord] = []

    for line_number, raw_line in enumerate(data_section.splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        parts = line.split(";", 5)

        if len(parts) not in {5, 6}:
            raise ValueError(
                f"Invalid initialization record at data section line {line_number}: {line!r}"
            )

        kind, hash_value, reference, content, type_marker = [part.strip() for part in parts[:5]]
        if kind == "TABLE":
            content, type_marker = _parse_table_fields(
                content, type_marker, layout=table_layout, line_number=line_number
            )
        semantic_tags = (
            tuple(tag.strip() for tag in parts[5].split(",") if tag.strip())
            if len(parts) == 6
            else ()
        )

        if kind not in _INITIALIZATION_RECORD_KINDS:
            raise ValueError(
                f"Invalid initialization record kind at data section line {line_number}: {kind!r}"
            )

        records.append(
            InitializationRecord(
                kind=kind,
                hash_value=hash_value,
                reference=reference,
                content=content,
                type_marker=type_marker,
                semantic_tags=semantic_tags,
            )
        )

    return records


def render_initialization_record(record: InitializationRecord) -> str:
    """Serialize one record; TABLE ends with generated parent, HITL caption."""
    fourth, fifth = record.content, record.type_marker
    if record.kind == "TABLE":
        fourth, fifth = fifth, fourth
    rendered = f"{record.kind};{record.hash_value};{record.reference};{fourth};{fifth}"
    if record.semantic_tags:
        return f"{rendered};{','.join(record.semantic_tags)}"
    return rendered


def render_initialization_records(records: list[InitializationRecord]) -> str:
    """Render a data section with an explicit TABLE layout for safe reimport.

    The comment disambiguates numeric captions and missing parents; without
    it, a legacy empty-caption record and a new numeric-caption record can
    have exactly the same bytes.
    """
    lines = [TABLE_RECORD_LAYOUT] if any(record.kind == "TABLE" for record in records) else []
    lines.extend(render_initialization_record(record) for record in records)
    return "\n".join(lines)


def _table_record_layout(data_section: str) -> str | None:
    layouts = {
        line.strip()[len(_TABLE_LAYOUT_PREFIX) :].strip()
        for line in data_section.splitlines()
        if line.strip().startswith(_TABLE_LAYOUT_PREFIX)
    }
    if not layouts:
        return None
    if len(layouts) != 1 or not layouts <= {"parent-caption", "caption-parent"}:
        raise ValueError("Invalid or conflicting table-record-layout comments in data section.")
    return layouts.pop()


def _parse_table_fields(
    fourth: str, fifth: str, *, layout: str | None, line_number: int
) -> tuple[str, str]:
    """Return semantic (caption, parent), migrating unmarked historical files.

    In unmarked records a sole reference-shaped value denotes the parent;
    a sole free-text value denotes the caption. Generated files declare their
    layout explicitly, so even reference-shaped captions round-trip exactly.
    """
    if layout == "parent-caption":
        return fifth, fourth
    if layout == "caption-parent":
        return fourth, fifth
    fourth_is_parent = bool(_TABLE_PARENT_REFERENCE.fullmatch(fourth))
    fifth_is_parent = bool(_TABLE_PARENT_REFERENCE.fullmatch(fifth))
    if fourth and fifth and fourth_is_parent == fifth_is_parent:
        raise ValueError(
            f"Ambiguous TABLE field order at data section line {line_number}; "
            f"add '{TABLE_RECORD_LAYOUT}' for parent in field 4, or "
            f"'{_TABLE_LAYOUT_PREFIX} caption-parent' for legacy parent in field 5."
        )
    if fifth_is_parent or (fourth and not fifth and not fourth_is_parent):
        return fourth, fifth
    return fifth, fourth


def _is_quoted(value: str) -> bool:
    return len(value) >= 2 and (
        value.startswith('"')
        and value.endswith('"')
        or value.startswith("'")
        and value.endswith("'")
    )
