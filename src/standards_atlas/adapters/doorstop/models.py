"""Adapter-internal Doorstop export models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from standards_atlas.domain.model.doorstop_attributes import (
    DoorstopReference,
)


@dataclass(frozen=True)
class DoorstopDocumentModel:
    prefix: str
    digits: int
    separator: str
    item_format: str
    target: Path
    parent: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DoorstopItemModel:
    uid: str
    level: str
    header: str
    text: str

    active: bool = True
    derived: bool = False
    normative: bool = False

    links: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    rationale: str = ""
    # ref: str | None = None
    references: tuple[DoorstopReference, ...] = ()
    reviewed: str | None = None

    attributes: dict[str, Any] = field(default_factory=dict)
