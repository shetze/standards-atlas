"""AST model for Atlas structure tokens."""

from __future__ import annotations

from dataclasses import dataclass

from standards_atlas.adapters.atlasdata.structure_types import AtlasItemType


@dataclass(frozen=True)
class StructureRange:
    start: int
    end: int


@dataclass(frozen=True)
class StructureToken:
    source: str
    reference_template: str
    item_type: AtlasItemType
    volume: str | None = None
    enum_prefix: str | None = None
    identifier_width: int | None = None
    ranges: tuple[StructureRange, ...] = ()
