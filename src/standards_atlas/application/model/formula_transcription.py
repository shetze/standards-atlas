"""Formula transcription enrichment artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FormulaTranscriptionProvenance(BaseModel):
    """Provenance recorded for one machine or human transcription."""

    model_config = ConfigDict(frozen=True)

    actor: str = Field(min_length=1)
    provider: str | None = None
    model: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FormulaTranscriptionArtifact(BaseModel):
    """Persisted enrichment independent of the canonical EngineeringDocument."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    formula_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)
    source_content_hash: str | None = None
    representation: Literal["latex"] = "latex"
    expression: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: FormulaTranscriptionProvenance
