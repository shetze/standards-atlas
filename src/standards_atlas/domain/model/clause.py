"""Clause model for Standards Atlas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from standards_atlas.domain.model.content import (
    ContentBlock,
    render_content_as_plain_text,
)
from standards_atlas.domain.model.doorstop_attributes import DoorstopItemAttributes
from standards_atlas.domain.model.identifiers import ClauseId, StandardReference
from standards_atlas.domain.model.reference_mention import ReferenceMention
from standards_atlas.domain.model.semantic_classification import SemanticClassification
from standards_atlas.domain.model.structural_context import StructuralContext
from standards_atlas.domain.model.structural_profile import StructuralProfile


class ClauseType(StrEnum):
    """Semantic type of a clause-like standard item."""

    TOC = "toc"
    CLAUSE = "clause"
    REQUIREMENT = "requirement"
    SCOPE = "scope"
    TERM = "term"
    OBJECTIVE = "objective"
    TABLE = "table"
    MISC = "misc"


class Clause(BaseModel):
    """A semantic clause-like item extracted from an engineering document.

    ``content`` is the sole canonical representation of protected clause content.
    Consumers that need a textual projection use :attr:`plain_text`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: ClauseId
    reference: StandardReference
    clause_type: ClauseType

    semantic_classification: SemanticClassification = SemanticClassification()
    structural_profile: StructuralProfile | None = None
    structural_context: StructuralContext | None = None
    reference_mentions: tuple[ReferenceMention, ...] = ()

    heading: str | None = None
    content: tuple[ContentBlock, ...] = ()
    parent_id: ClauseId | None = None
    source_token: str | None = None

    enum_prefix: str | None = None
    identifier_width: int | None = None

    doorstop: DoorstopItemAttributes | None = None

    @property
    def plain_text(self) -> str:
        """Return a stable plain-text projection of structured content."""
        return render_content_as_plain_text(self.content)
