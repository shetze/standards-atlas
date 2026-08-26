"""Rebuildable publication view for a logical multi-part document family."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model import EngineeringDocument


class ComposedDocumentView(BaseModel):
    """Publication-only composition of canonical physical part documents."""

    model_config = ConfigDict(frozen=True)

    family_key: str = Field(min_length=1)
    part_keys: tuple[str, ...] = Field(min_length=1)
    document: EngineeringDocument
