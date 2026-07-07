"""Expand compact Atlas structure tokens into normalized structure items."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from standards_atlas.adapters.atlasdata.structure_ast import StructureToken
from standards_atlas.adapters.atlasdata.structure_lexer import lex_structure_token
from standards_atlas.adapters.atlasdata.structure_parser import parse_lexed_structure_token
from standards_atlas.adapters.atlasdata.structure_types import ( AtlasItemType, TYPE_PREFIXES, )


@dataclass(frozen=True)
class StructureItem:
    """One expanded item from an Atlas structure token."""

    visible_reference: str
    item_type: AtlasItemType
    volume: str | None = None
    enum_prefix: str | None = None
    identifier_width: int | None = None
    source_token: str | None = None
    publication_year: int | None = None


_RANGE_PATTERN = re.compile(r"\{(?P<start>\d+)\.\.(?P<end>\d+)\}")


def expand_structure_line(line: str) -> list[StructureItem]:
    """Expand a whitespace-separated Atlas structure line.

    If the first token is a four-digit year, it is treated as the
    publication year for all following structure items in that line.
    """
    tokens = line.split()

    if not tokens:
        return []

    publication_year: int | None = None

    if _is_publication_year_token(tokens[0]):
        publication_year = int(tokens[0])
        tokens = tokens[1:]

    items: list[StructureItem] = []

    for token in tokens:
        items.extend(
            expand_structure_token(
                token,
                publication_year=publication_year,
            )
        )

    return items

def expand_structure_token(
    token: str,
    *,
    publication_year: int | None = None,
) -> list[StructureItem]:
    """Expand a single Atlas structure token."""
    lexed = lex_structure_token(token)
    parsed = parse_lexed_structure_token(lexed)

    return expand_parsed_structure_token(
        parsed,
        publication_year=publication_year,
    )

def expand_parsed_structure_token(
    token: StructureToken,
    *,
    publication_year: int | None = None,
) -> list[StructureItem]:
    """Expand a parsed structure token into structure items."""
    expanded_references = _expand_reference_template(token.reference_template)

    return [
        StructureItem(
            visible_reference=reference,
            item_type=token.item_type,
            volume=token.volume,
            enum_prefix=token.enum_prefix,
            identifier_width=token.identifier_width,
            source_token=token.source,
            publication_year=publication_year,
        )
        for reference in expanded_references
    ]

def _is_publication_year_token(token: str) -> bool:
    return len(token) == 4 and token.isdigit()

def _expand_reference_template(template: str) -> list[str]:
    match = _RANGE_PATTERN.search(template)

    if match is None:
        return [template]

    start = int(match.group("start"))
    end = int(match.group("end"))

    if start > end:
        raise ValueError(f"Invalid descending range in structure token: {template!r}")

    expanded: list[str] = []

    for value in range(start, end + 1):
        expanded_template = template[: match.start()] + str(value) + template[match.end():]
        expanded.extend(_expand_reference_template(expanded_template))

    return expanded

__all__ = [
    "AtlasItemType",
    "StructureItem",
    "expand_structure_line",
    "expand_structure_token",
    "expand_parsed_structure_token",
]
