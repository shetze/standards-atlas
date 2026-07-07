"""Shared types for Atlas structure parsing."""

from __future__ import annotations

from enum import StrEnum


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
