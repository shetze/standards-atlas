"""Contextual routing concepts for scope declarations and semantic references.

The models in this module deliberately sit beside the deterministic structural
signals.  Structural scope/reference detection records what is present in the
source; contextual routing records the interpreted reach or role of that
source evidence for later CBox projection.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.domain.model.reference_mention import ReferenceTarget


class ScopeReachKind(StrEnum):
    """Granularity at which a scope declaration governs knowledge."""

    DOCUMENT = "document"
    PART = "part"
    SUBTREE = "subtree"
    CLAUSE = "clause"


class ScopeReach(BaseModel):
    """One interpreted target region governed by a scope declaration.

    ``document_key`` may be omitted for targets in the source document.  A
    part reach requires ``part``; subtree/clause reaches require an addressable
    clause via ``clause_id`` or ``reference``.  This keeps routing useful both
    before and after all references have been resolved to internal clause IDs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ScopeReachKind
    document_key: str | None = None
    part: str | None = None
    clause_id: str | None = None
    reference: str | None = None

    @model_validator(mode="after")
    def target_matches_reach_kind(self) -> ScopeReach:
        if self.kind == ScopeReachKind.DOCUMENT:
            if self.part or self.clause_id or self.reference:
                raise ValueError("document scope reach cannot address a part or clause")
            return self

        if self.kind == ScopeReachKind.PART:
            if not self.part:
                raise ValueError("part scope reach requires part")
            if self.clause_id or self.reference:
                raise ValueError("part scope reach cannot address a clause")
            return self

        if not self.clause_id and not self.reference:
            raise ValueError(f"{self.kind.value} scope reach requires clause_id or reference")
        return self


class ScopeDeclaration(BaseModel):
    """Meta-level applicability context governing one or more knowledge regions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_clause_id: str = Field(min_length=1)
    reaches: tuple[ScopeReach, ...] = Field(min_length=1)
    conditions: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    qualifications: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


class ReferenceRole(StrEnum):
    """Semantic routing role played by a reference in its source context."""

    DEFINES = "defines"
    CONSTRAINS = "constrains"
    REQUIRES = "requires"
    PROVIDES_PROCEDURE = "provides_procedure"
    PROVIDES_EXCEPTION = "provides_exception"
    PROVIDES_APPLICABILITY = "provides_applicability"
    PROVIDES_EVIDENCE = "provides_evidence"
    REFINES = "refines"
    DEPENDS_ON = "depends_on"
    OTHER = "other"


class ReferenceRouting(BaseModel):
    """Interpreted semantic routing edge created from reference evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_clause_id: str = Field(min_length=1)
    target: ReferenceTarget
    role: ReferenceRole
    evidence: tuple[str, ...] = ()


class ContextRouting(BaseModel):
    """CBox-oriented routing interpretation for one clause or document region."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scopes: tuple[ScopeDeclaration, ...] = ()
    references: tuple[ReferenceRouting, ...] = ()
