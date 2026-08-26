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
    """One public initialization record from an Atlas data file."""

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
    """Parse TOC and TEXT records after the data marker."""
    if _DATA_MARKER not in text:
        return []

    _, data_section = text.split(_DATA_MARKER, 1)

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


def _is_quoted(value: str) -> bool:
    return len(value) >= 2 and (
        value.startswith('"')
        and value.endswith('"')
        or value.startswith("'")
        and value.endswith("'")
    )
