"""Clause model for Standards Atlas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

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
    """A semantic clause-like item extracted from a standard."""

    model_config = ConfigDict(frozen=True)

    id: ClauseId
    reference: StandardReference
    clause_type: ClauseType

    semantic_roles: tuple[SemanticRole, ...] = ()

    title: str | None = None
    text: str | None = None

    parent_id: ClauseId | None = None
    source_token: str | None = None

    volume: str | None = None
    enum_prefix: str | None = None
    identifier_width: int | None = None
