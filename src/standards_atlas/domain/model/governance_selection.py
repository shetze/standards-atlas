"""Engineering-context contract for governance selection.

The profile captures user-supplied context and deterministic selection hints. It
is intentionally independent from Gemara and from any evaluator/runtime model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from standards_atlas.domain.model.semantic_classification import (
    KnowledgeKind,
    ProcessFunction,
    StatementFunction,
)


class GovernanceContext(BaseModel):
    """Domain-neutral engineering context for one governance use case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    domain: str = Field(min_length=1)
    system_types: tuple[str, ...] = Field(default=(), alias="system-types")
    lifecycle_phases: tuple[str, ...] = Field(default=(), alias="lifecycle-phases")
    integrity_levels: tuple[str, ...] = Field(default=(), alias="integrity-levels")
    roles: tuple[str, ...] = ()
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator(
        "domain",
        "system_types",
        "lifecycle_phases",
        "integrity_levels",
        "roles",
        mode="before",
    )
    @classmethod
    def _reject_blank_vocabulary(cls, value: Any) -> Any:
        if isinstance(value, str):
            if not value.strip():
                raise ValueError("governance context vocabulary values must be non-empty")
            return value.strip()
        if isinstance(value, (list, tuple)):
            normalized = []
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError("governance context vocabulary values must be non-empty")
                normalized.append(item.strip())
            return tuple(normalized)
        return value

    @model_validator(mode="after")
    def _vocabulary_is_unique(self) -> GovernanceContext:
        for name in ("system_types", "lifecycle_phases", "integrity_levels", "roles"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"governance context {name.replace('_', '-')} must be unique")
        if any(not key.strip() for key in self.attributes):
            raise ValueError("governance context attribute names must be non-empty")
        return self


class GovernanceStandardSelection(BaseModel):
    """Explicit standard-family/document boundaries for selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    @field_validator("include", "exclude", mode="before")
    @classmethod
    def _normalize_document_keys(cls, value: Any) -> Any:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            return value
        normalized = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("standard selection keys must be non-empty strings")
            normalized.append(item.strip())
        return tuple(normalized)

    @model_validator(mode="after")
    def _sets_are_consistent(self) -> GovernanceStandardSelection:
        if len(self.include) != len(set(self.include)):
            raise ValueError("included standards must be unique")
        if len(self.exclude) != len(set(self.exclude)):
            raise ValueError("excluded standards must be unique")
        overlap = sorted(set(self.include) & set(self.exclude))
        if overlap:
            raise ValueError(
                "standards cannot be both included and excluded: " + ", ".join(overlap)
            )
        return self


class GovernanceSemanticSelection(BaseModel):
    """Optional deterministic semantic dimensions used by later candidate analysis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    process_functions: tuple[ProcessFunction, ...] = Field(default=(), alias="process-functions")
    knowledge_kinds: tuple[KnowledgeKind, ...] = Field(default=(), alias="knowledge-kinds")
    statement_functions: tuple[StatementFunction, ...] = Field(
        default=(), alias="statement-functions"
    )

    @model_validator(mode="after")
    def _dimensions_are_unique(self) -> GovernanceSemanticSelection:
        for name in ("process_functions", "knowledge_kinds", "statement_functions"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"selection {name.replace('_', '-')} must be unique")
        return self


class GovernanceApplicabilityContext(BaseModel):
    """Selection-time applicability intent, without Gemara policy semantics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    require_present: bool = Field(default=False, alias="require-present")
    polarity: str | None = None

    @field_validator("polarity")
    @classmethod
    def _validate_polarity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"included", "excluded"}:
            raise ValueError("applicability polarity must be 'included' or 'excluded'")
        return normalized

    @model_validator(mode="after")
    def _polarity_requires_presence(self) -> GovernanceApplicabilityContext:
        if self.polarity is not None and not self.require_present:
            raise ValueError("applicability polarity requires require-present: true")
        return self


class GovernanceSelectionProfile(BaseModel):
    """Versioned input contract describing one engineering governance use case."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_version: int = Field(default=1, alias="schema-version")
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = ""
    context: GovernanceContext
    standards: GovernanceStandardSelection = Field(default_factory=GovernanceStandardSelection)
    selection: GovernanceSemanticSelection = Field(default_factory=GovernanceSemanticSelection)
    applicability: GovernanceApplicabilityContext = Field(
        default_factory=GovernanceApplicabilityContext
    )

    @field_validator("schema_version")
    @classmethod
    def _supported_schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported governance selection profile schema-version; expected 1")
        return value

    @field_validator("id", "version", "description", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class GovernanceCandidateDecision(StrEnum):
    """Deterministic tri-state outcome for one policy candidate."""

    SELECTED = "selected"
    EXCLUDED = "excluded"
    UNDETERMINED = "undetermined"


class GovernanceCandidateSignal(BaseModel):
    """One auditable selector signal contributing to a candidate decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: str = Field(min_length=1)
    outcome: GovernanceCandidateDecision
    reason: str = Field(min_length=1)
    expected: tuple[str, ...] = ()
    observed: tuple[str, ...] = ()


class GovernancePolicyCandidate(BaseModel):
    """One ControlCatalog control evaluated against a selection profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    control_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_clause_ids: tuple[str, ...] = Field(min_length=1)
    assessment_requirement_ids: tuple[str, ...] = Field(min_length=1)
    decision: GovernanceCandidateDecision
    signals: tuple[GovernanceCandidateSignal, ...] = Field(min_length=1)


class GovernanceCandidateAnalysis(BaseModel):
    """Deterministic review artifact produced for one selection profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(default=1, alias="schema-version")
    profile_id: str = Field(alias="profile-id", min_length=1)
    profile_version: str = Field(alias="profile-version", min_length=1)
    documents: tuple[str, ...] = ()
    selected: int = 0
    excluded: int = 0
    undetermined: int = 0
    candidates: tuple[GovernancePolicyCandidate, ...] = ()
