"""Engineering-context contract for governance selection.

The profile captures user-supplied context and deterministic selection hints. It
is intentionally independent from Gemara and from any evaluator/runtime model.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from standards_atlas.domain.model.governance_subject_groups import GovernanceSubjectGroupProfileRef
from standards_atlas.domain.model.semantic_classification import (
    KnowledgeKind,
    ProcessFunction,
    StatementFunction,
)
from standards_atlas.domain.model.subject_normalization import normalize_subject_label

_SUBJECT_GROUP_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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
    """Optional orthogonal semantic dimensions used by candidate analysis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    process_functions: tuple[ProcessFunction, ...] = Field(default=(), alias="process-functions")
    knowledge_kinds: tuple[KnowledgeKind, ...] = Field(default=(), alias="knowledge-kinds")
    statement_functions: tuple[StatementFunction, ...] = Field(
        default=(), alias="statement-functions"
    )
    primary_subjects: tuple[str, ...] = Field(default=(), alias="primary-subjects")
    primary_subject_groups: tuple[str, ...] = Field(default=(), alias="primary-subject-groups")
    subject_group_profile: GovernanceSubjectGroupProfileRef | None = Field(
        default=None, alias="subject-group-profile"
    )

    @field_validator("primary_subjects", mode="before")
    @classmethod
    def _normalize_primary_subjects(cls, value: Any) -> Any:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            return value
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("selection primary-subjects must be non-empty strings")
            label = normalize_subject_label(item)
            if not label:
                raise ValueError("selection primary-subjects must normalize to non-empty labels")
            normalized.append(label)
        return tuple(normalized)

    @field_validator("primary_subject_groups", mode="before")
    @classmethod
    def _normalize_subject_groups(cls, value: Any) -> Any:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            return value
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("selection primary-subject-groups must be non-empty strings")
            group_id = item.strip()
            if not _SUBJECT_GROUP_ID.fullmatch(group_id):
                raise ValueError("selection primary-subject-groups must use lower-case kebab-case")
            normalized.append(group_id)
        return tuple(normalized)

    @model_validator(mode="after")
    def _dimensions_are_consistent(self) -> GovernanceSemanticSelection:
        for name in (
            "process_functions",
            "knowledge_kinds",
            "statement_functions",
            "primary_subjects",
            "primary_subject_groups",
        ):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"selection {name.replace('_', '-')} must be unique")
        if self.primary_subject_groups and self.subject_group_profile is None:
            raise ValueError("selection primary-subject-groups requires subject-group-profile")
        return self


class GovernanceSelectionProfile(BaseModel):
    """Versioned input contract describing one engineering governance use case."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_version: int = Field(default=2, alias="schema-version")
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = ""
    context: GovernanceContext
    standards: GovernanceStandardSelection = Field(default_factory=GovernanceStandardSelection)
    selection: GovernanceSemanticSelection = Field(default_factory=GovernanceSemanticSelection)

    @field_validator("schema_version")
    @classmethod
    def _supported_schema(cls, value: int) -> int:
        if value != 2:
            raise ValueError("unsupported governance selection profile schema-version; expected 2")
        return value

    @field_validator("id", "version", "description", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class GovernanceCandidateDecision(StrEnum):
    """Deterministic tri-state outcome for governance selection."""

    SELECTED = "selected"
    EXCLUDED = "excluded"
    UNDETERMINED = "undetermined"


class GovernanceCandidateSignal(BaseModel):
    """One auditable selector signal contributing to a decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: str = Field(min_length=1)
    outcome: GovernanceCandidateDecision
    reason: str = Field(min_length=1)
    expected: tuple[str, ...] = ()
    observed: tuple[str, ...] = ()


class GovernanceSubjectSelectionResolution(BaseModel):
    """Resolved primary-subject selection recorded with candidate analysis."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    subject_group_profile: GovernanceSubjectGroupProfileRef | None = Field(
        default=None, alias="subject-group-profile"
    )
    primary_subject_groups: tuple[str, ...] = Field(default=(), alias="primary-subject-groups")
    explicit_primary_subjects: tuple[str, ...] = Field(
        default=(), alias="explicit-primary-subjects"
    )
    effective_primary_subjects: tuple[str, ...] = Field(
        default=(), alias="effective-primary-subjects"
    )


class GovernanceClauseSelectionResult(BaseModel):
    """Clause-local evaluation of all active semantic selection dimensions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: str = Field(alias="clause-id", min_length=1)
    decision: GovernanceCandidateDecision
    primary_subject: str | None = Field(default=None, alias="primary-subject")
    ambiguous_primary_subjects: tuple[str, ...] = Field(
        default=(), alias="ambiguous-primary-subjects"
    )
    signals: tuple[GovernanceCandidateSignal, ...] = ()


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
    matching_clause_ids: tuple[str, ...] = Field(default=(), alias="matching-clause-ids")
    undetermined_clause_ids: tuple[str, ...] = Field(default=(), alias="undetermined-clause-ids")
    clause_results: tuple[GovernanceClauseSelectionResult, ...] = Field(
        default=(), alias="clause-results"
    )

    @property
    def matching_primary_subjects(self) -> tuple[str, ...]:
        """Return distinct primary subjects from fully matching clauses."""

        matching = set(self.matching_clause_ids)
        return tuple(
            sorted(
                {
                    result.primary_subject
                    for result in self.clause_results
                    if result.clause_id in matching and result.primary_subject is not None
                }
            )
        )


class GovernanceCandidateAnalysis(BaseModel):
    """Deterministic review artifact produced for one selection profile."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_version: int = Field(default=2, alias="schema-version")
    profile_id: str = Field(alias="profile-id", min_length=1)
    profile_version: str = Field(alias="profile-version", min_length=1)
    documents: tuple[str, ...] = ()
    subject_selection: GovernanceSubjectSelectionResolution = Field(
        default_factory=GovernanceSubjectSelectionResolution,
        alias="subject-selection",
    )
    selected: int = 0
    excluded: int = 0
    undetermined: int = 0
    candidates: tuple[GovernancePolicyCandidate, ...] = ()

    @field_validator("schema_version")
    @classmethod
    def _supported_analysis_schema(cls, value: int) -> int:
        if value != 2:
            raise ValueError("unsupported governance candidate analysis schema-version; expected 2")
        return value
