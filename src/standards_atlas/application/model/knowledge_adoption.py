"""Versioned, explicit transfer from run artifacts to canonical enrichments."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from standards_atlas.application.model.source_structure import SourceStructureFact
from standards_atlas.domain.model.enrichment_patch import AttributeChange, ClauseEnrichmentPatch
from standards_atlas.domain.model.knowledge_state import GeneratedAttribute


class ClauseKnowledgeCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    heading: str | None = None
    patch: ClauseEnrichmentPatch
    attributes: tuple[GeneratedAttribute, ...]
    not_evaluated: tuple[str, ...] = ()
    source_requirements: tuple[SourceStructureFact, ...] = ()

    @model_serializer(mode="wrap")
    def omit_legacy_empty_source_requirements(self, handler):
        payload = handler(self)
        if not self.source_requirements:
            payload.pop("source_requirements", None)
        return payload


class KnowledgeAdoptionBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0", "1.1"] = "1.0"
    policy_id: Literal["canonical-knowledge-adoption-v1"] = "canonical-knowledge-adoption-v1"
    source_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_clause_count: int = Field(ge=0)
    unqualified_clause_count: int = Field(ge=0)
    candidates: tuple[ClauseKnowledgeCandidate, ...]

    @model_validator(mode="after")
    def unique_candidates(self) -> KnowledgeAdoptionBatch:
        if self.schema_version == "1.0" and any(
            item.source_requirements for item in self.candidates
        ):
            raise ValueError("source-bound adoption requires batch schema 1.1")
        keys = [(item.document_key, item.clause_id) for item in self.candidates]
        if len(keys) != len(set(keys)):
            raise ValueError("adoption candidates must have unique document/clause coordinates")
        if len(keys) + self.unqualified_clause_count != self.selected_clause_count:
            raise ValueError("adoption accounting does not cover the selected clauses")
        return self


class ClauseAdoptionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_key: str
    clause_id: str
    changes: tuple[AttributeChange, ...]
    not_evaluated: tuple[str, ...] = ()


class KnowledgeAdoptionReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    policy_id: Literal["canonical-knowledge-adoption-v1"] = "canonical-knowledge-adoption-v1"
    source_id: str
    source_sha256: str
    write_requested: bool
    selected_clause_count: int
    unqualified_clause_count: int
    addressed_clause_count: int
    changed_document_keys: tuple[str, ...]
    written_document_keys: tuple[str, ...]
    status_counts: dict[str, int]
    clauses: tuple[ClauseAdoptionResult, ...]
