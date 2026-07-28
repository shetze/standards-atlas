"""Application contracts and models for read-only clause access."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model import ClauseType, DocumentType, SemanticRole


class SamplingStrategy(StrEnum):
    """Supported deterministic sampling strategies."""

    RANDOM = "random"
    BALANCED_BY_DOCUMENT = "balanced_by_document"
    REPRESENTATIVE_STRATIFIED = "representative_stratified"


class DocumentDescriptor(BaseModel):
    """Metadata exposed for a persisted engineering document."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    document_type: DocumentType
    year: int | None = None
    version: str | None = None
    clause_count: int = Field(ge=0)


class ClauseDescriptor(BaseModel):
    """Stable, transport-neutral representation of a clause."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    clause_reference: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    clause_type: ClauseType
    title: str | None = None
    text: str = ""
    parent_id: str | None = None
    semantic_roles: tuple[SemanticRole, ...] = ()


class ClauseFilter(BaseModel):
    """Filter criteria shared by search, listing, and sampling."""

    model_config = ConfigDict(frozen=True)

    document_keys: tuple[str, ...] = ()
    document_types: tuple[DocumentType, ...] = ()
    clause_types: tuple[ClauseType, ...] = ()
    semantic_roles: tuple[SemanticRole, ...] = ()
    language: str | None = None
    min_text_length: int | None = Field(default=None, ge=0)
    max_text_length: int | None = Field(default=None, ge=0)


class ClauseProvider(Protocol):
    """Read-only application port for document and clause discovery."""

    def list_documents(self) -> tuple[DocumentDescriptor, ...]:
        """Return all available documents in stable order."""
        ...

    def get_clause(self, clause_id: str) -> ClauseDescriptor:
        """Return one clause by stable clause identifier."""
        ...

    def list_clauses(
        self,
        *,
        filters: ClauseFilter | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[ClauseDescriptor, ...]:
        """Return clauses matching the supplied filters."""
        ...

    def search_clauses(
        self,
        query: str,
        *,
        filters: ClauseFilter | None = None,
        limit: int = 20,
    ) -> tuple[ClauseDescriptor, ...]:
        """Search clauses by title and plain text."""
        ...

    def sample_clauses(
        self,
        *,
        count: int,
        strategy: SamplingStrategy = SamplingStrategy.RANDOM,
        filters: ClauseFilter | None = None,
        seed: int = 0,
    ) -> tuple[ClauseDescriptor, ...]:
        """Return a reproducible clause sample."""
        ...
