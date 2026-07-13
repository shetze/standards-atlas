"""Parse lexed Atlas structure tokens into StructureToken AST nodes."""

from __future__ import annotations

import re

from standards_atlas.adapters.atlasdata.structure_ast import StructureRange, StructureToken
from standards_atlas.adapters.atlasdata.structure_lexer import LexedStructureToken
from standards_atlas.adapters.atlasdata.structure_types import TYPE_PREFIXES, AtlasItemType

_RANGE_PATTERN = re.compile(r"\{(?P<start>\d+)\.\.(?P<end>\d+)\}")


def parse_lexed_structure_token(token: LexedStructureToken) -> StructureToken:
    """Parse a lexed structure token."""
    body = token.body

    item_type, body = _parse_type_prefix(body)
    identifier_width, body = _parse_identifier_width_marker(body)
    ranges = _parse_ranges(body)

    return StructureToken(
        source=token.source,
        reference_template=body,
        item_type=item_type,
        volume=token.volume,
        enum_prefix=token.enum_prefix,
        identifier_width=identifier_width,
        ranges=tuple(ranges),
    )


def _parse_type_prefix(body: str) -> tuple[AtlasItemType, str]:
    if not body:
        raise ValueError("Structure token is missing a clause reference.")

    prefix = body[0]

    if prefix in TYPE_PREFIXES:
        remainder = body[1:]

        if not remainder:
            raise ValueError(f"Structure token is missing a reference after prefix {prefix!r}.")

        return TYPE_PREFIXES[prefix], remainder

    return AtlasItemType.TOC, body


def _parse_identifier_width_marker(body: str) -> tuple[int | None, str]:
    if ".+" not in body:
        return None, body

    return 3, body.replace(".+", ".", 1)


def _parse_ranges(body: str) -> list[StructureRange]:
    ranges: list[StructureRange] = []

    for match in _RANGE_PATTERN.finditer(body):
        start = int(match.group("start"))
        end = int(match.group("end"))

        if start > end:
            raise ValueError(f"Invalid descending range in structure token: {body!r}")

        ranges.append(StructureRange(start=start, end=end))

    return ranges
