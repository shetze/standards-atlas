"""Clause model for Standards Atlas."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.domain.model.content import (
    ContentBlock,
    render_content_as_plain_text,
)
from standards_atlas.domain.model.doorstop_attributes import DoorstopItemAttributes
from standards_atlas.domain.model.identifiers import ClauseId, StandardReference
from standards_atlas.domain.model.semantic_role import SemanticRole


class ClauseType(StrEnum):
    """Semantic type of a clause-like standard item."""

    TOC = "toc"
    CLAUSE = "clause"
    REQUIREMENT = "requirement"
    SCOPE = "scope"
    TERM = "term"
    OBJECTIVE = "objective"
    MISC = "misc"


class Clause(BaseModel):
    """A semantic clause-like item extracted from an engineering document.

    ``content`` is the canonical protected-content representation. ``text``
    remains as a deprecated input compatibility field and is converted into a
    single TextBlock when no structured content is supplied.
    """

    model_config = ConfigDict(frozen=True)

    id: ClauseId
    reference: StandardReference
    clause_type: ClauseType

    semantic_roles: tuple[SemanticRole, ...] = ()

    title: str | None = None
    content: tuple[ContentBlock, ...] = ()
    text: str | None = Field(default=None, exclude=True, repr=False)

    parent_id: ClauseId | None = None
    source_token: str | None = None

    volume: str | None = None
    enum_prefix: str | None = None
    identifier_width: int | None = None

    doorstop: DoorstopItemAttributes | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_text(cls, data: Any) -> Any:
        """Convert a legacy text field into canonical structured content."""
        if not isinstance(data, dict):
            return data

        text = data.get("text")
        content = data.get("content")

        if text and not content:
            migrated = dict(data)
            migrated["content"] = [
                {
                    "id": _legacy_text_block_id(migrated, text),
                    "type": "text",
                    "text": text,
                    "source_evidence": [],
                }
            ]
            return migrated

        return data

    @property
    def plain_text(self) -> str:
        """Return a stable plain-text projection of structured content."""
        return render_content_as_plain_text(self.content)


def _legacy_text_block_id(data: dict[str, Any], text: str) -> str:
    clause_id = data.get("id")
    if isinstance(clause_id, dict):
        clause_id = clause_id.get("value")
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"{clause_id or 'clause'}-text-{digest}"
