"""Expand compact Atlas structure tokens into normalized structure items."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


class AtlasItemType(StrEnum):
    TOC = "toc"
    REQUIREMENT = "requirement"
    SCOPE = "scope"
    TERM = "term"
    OBJECTIVE = "objective"
    CLAUSE = "clause"
    MISC = "misc"


TYPE_PREFIXES: dict[str, AtlasItemType] = {
    "r": AtlasItemType.REQUIREMENT,
    "s": AtlasItemType.SCOPE,
    "t": AtlasItemType.TERM,
    "o": AtlasItemType.OBJECTIVE,
    "c": AtlasItemType.CLAUSE,
    "m": AtlasItemType.MISC,
}


@dataclass(frozen=True)
class StructureItem:
    """One expanded item from an Atlas structure token."""

    visible_reference: str
    item_type: AtlasItemType
    volume: str | None = None
    enum_prefix: str | None = None
    identifier_width: int | None = None
    source_token: str | None = None


_RANGE_PATTERN = re.compile(r"\{(?P<start>\d+)\.\.(?P<end>\d+)\}")


def expand_structure_line(line: str) -> list[StructureItem]:
    """Expand a whitespace-separated Atlas structure line."""
    items: list[StructureItem] = []

    for token in line.split():
        items.extend(expand_structure_token(token))

    return items


def expand_structure_token(token: str) -> list[StructureItem]:
    """Expand a single Atlas structure token.

    Examples:
        r5.1.2.{1..3} -> 5.1.2.1, 5.1.2.2, 5.1.2.3
        10:A -> A
        8-r11.4.7.{1..2} -> 11.4.7.1, 11.4.7.2 with volume 8
        0-4.+{1..2} -> 4.1, 4.2 with identifier_width 3
    """
    if not token or token.isspace():
        raise ValueError("Structure token must not be empty.")

    source_token = token
    volume, token = _split_volume(token)
    enum_prefix, token = _split_enum_prefix(token)
    item_type, token = _split_type_prefix(token)
    identifier_width, token = _split_identifier_width_marker(token)

    expanded_references = _expand_ranges(token)

    return [
        StructureItem(
            visible_reference=reference,
            item_type=item_type,
            volume=volume,
            enum_prefix=enum_prefix,
            identifier_width=identifier_width,
            source_token=source_token,
        )
        for reference in expanded_references
    ]


def _split_volume(token: str) -> tuple[str | None, str]:
    if "-" not in token:
        return None, token

    prefix, remainder = token.split("-", 1)

    if not prefix:
        raise ValueError(f"Invalid volume prefix in structure token: {token!r}")

    return prefix, remainder


def _split_enum_prefix(token: str) -> tuple[str | None, str]:
    if ":" not in token:
        return None, token

    prefix, remainder = token.split(":", 1)

    if not prefix or not remainder:
        raise ValueError(f"Invalid enum prefix in structure token: {token!r}")

    return prefix, remainder


def _split_type_prefix(token: str) -> tuple[AtlasItemType, str]:
    if not token:
        raise ValueError("Structure token is missing a clause reference.")

    prefix = token[0]

    if prefix in TYPE_PREFIXES:
        remainder = token[1:]

        if not remainder:
            raise ValueError(f"Structure token is missing a reference after prefix {prefix!r}.")

        return TYPE_PREFIXES[prefix], remainder

    return AtlasItemType.TOC, token


def _split_identifier_width_marker(token: str) -> tuple[int | None, str]:
    if ".+" not in token:
        return None, token

    token = token.replace(".+", ".", 1)
    return 3, token


def _expand_ranges(token: str) -> list[str]:
    match = _RANGE_PATTERN.search(token)

    if match is None:
        return [token]

    start = int(match.group("start"))
    end = int(match.group("end"))

    if start > end:
        raise ValueError(f"Invalid descending range in structure token: {token!r}")

    expanded: list[str] = []

    for value in range(start, end + 1):
        expanded_token = (
            token[: match.start()]
            + str(value)
            + token[match.end() :]
        )
        expanded.extend(_expand_ranges(expanded_token))

    return expanded
