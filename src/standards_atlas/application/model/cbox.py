"""Read-only CBox contract; values and their authority are never inferred by a renderer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model.knowledge_state import ConfirmedAttribute, GeneratedAttribute


class CBoxAttribute(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    availability: Literal["known", "unknown", "not_evaluated", "partial"]
    origin: Literal["generated", "confirmed", "unattributed", "not_evaluated", "partial"]
    value: object = None
    generated: GeneratedAttribute | None = None
    confirmed: ConfirmedAttribute | None = None


class CBoxEnrichments(BaseModel):
    """Local, potentially protected projection of accepted canonical knowledge."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    attributes: tuple[CBoxAttribute, ...] = ()


class CBoxReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    frame: str
    renderer_version: str
    knowledge_domain: str
    document_keys: tuple[str, ...]
    clause_count: int
    canonical_sha256: str
    framed_sha256: str
    availability_counts: dict[str, int] = Field(default_factory=dict)
    clauses: tuple[dict, ...]
