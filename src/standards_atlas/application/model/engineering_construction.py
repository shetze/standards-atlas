"""Assurance contract for constructing an EngineeringDocument from alignment."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConstructionDiagnostic(BaseModel):
    """One deterministic finding produced by the construction contract."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    clause_ids: tuple[str, ...] = ()
    normalized_item_ids: tuple[str, ...] = ()


class ConstructionCoverage(BaseModel):
    """Accounting of normalized items consumed or deliberately excluded."""

    model_config = ConfigDict(frozen=True)

    active_items: int = 0
    assigned_items: int = 0
    structural_heading_items: int = 0
    following_label_items: int = 0
    front_matter_items: int = 0
    between_clause_items: int = 0
    back_matter_items: int = 0
    unassigned_items: int = 0


class EngineeringConstructionContract(BaseModel):
    """Persistable proof that EngineeringDocument construction was validated."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    valid: bool
    normalized_document_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    alignment_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    automatic_alignment_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_alignment_used: bool = False
    reviewed_alignment_unchanged: bool = True
    coverage: ConstructionCoverage
    diagnostics: tuple[ConstructionDiagnostic, ...] = ()
