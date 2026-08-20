"""Deterministic structural context materialized for taxonomy and ontology."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StructuralNodeKind(StrEnum):
    NODE = "node"
    LEAF = "leaf"


class StructuralReferenceEdge(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_clause_id: str = Field(min_length=1)
    target_clause_id: str | None = None
    target_reference: str | None = None
    status: str = Field(min_length=1)
    surface_text: str = Field(min_length=1)


class StructuralScopeMention(BaseModel):
    """Structure-derived scope signal preserved for ontology interpretation."""

    model_config = ConfigDict(frozen=True)
    source: str = Field(min_length=1)
    surface_text: str = Field(min_length=1)
    direction_hint: str | None = None
    cardinality: int | None = Field(default=None, ge=1)
    status: str = Field(min_length=1)


class StructuralScopeEdge(BaseModel):
    """Resolved or deferred structural reach of a scope statement."""

    model_config = ConfigDict(frozen=True)
    source_clause_id: str = Field(min_length=1)
    target_clause_id: str | None = None
    direction: str | None = None
    status: str = Field(min_length=1)
    surface_text: str = Field(min_length=1)


class StructuralSiblingContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    index: int = Field(ge=0)
    count: int = Field(ge=1)
    is_first: bool
    is_last: bool
    previous_clause_id: str | None = None
    next_clause_id: str | None = None


class StructuralAncestor(BaseModel):
    model_config = ConfigDict(frozen=True)
    clause_id: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    heading: str | None = None


class StructuralContext(BaseModel):
    """Complete structure-derived context for one clause."""

    model_config = ConfigDict(frozen=True)
    node_kind: StructuralNodeKind
    ancestors: tuple[StructuralAncestor, ...] = ()
    sibling: StructuralSiblingContext | None = None
    child_clause_ids: tuple[str, ...] = ()
    contextual_content_clause_ids: tuple[str, ...] = ()
    references: tuple[StructuralReferenceEdge, ...] = ()
    scope_mentions: tuple[StructuralScopeMention, ...] = ()
    scopes: tuple[StructuralScopeEdge, ...] = ()
