"""Versioned grouping contract for governance primary-subject selection."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from standards_atlas.domain.model.subject_normalization import normalize_subject_label

_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class GovernanceSubjectGroupProfileRef(BaseModel):
    """Identity of one versioned subject-group profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)

    @field_validator("id", "version", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("subject-group profile id must use lower-case kebab-case")
        return value


class GovernanceSubjectGroupDefinition(BaseModel):
    """One named union of discrete normalized primary subjects."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    description: str = ""
    subjects: tuple[str, ...] = Field(min_length=1)

    @field_validator("id", "description", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("subject-group id must use lower-case kebab-case")
        return value

    @field_validator("subjects", mode="before")
    @classmethod
    def _normalize_subjects(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("subject-group subjects must be non-empty strings")
            label = normalize_subject_label(item)
            if not label:
                raise ValueError("subject-group subjects must normalize to non-empty labels")
            normalized.append(label)
        return tuple(normalized)

    @model_validator(mode="after")
    def _subjects_are_unique(self) -> GovernanceSubjectGroupDefinition:
        if len(self.subjects) != len(set(self.subjects)):
            raise ValueError(f"subject-group {self.id} subjects must be unique")
        return self


class GovernanceSubjectGroupProfile(BaseModel):
    """Versioned subject grouping used by governance selection profiles."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_version: int = Field(default=1, alias="schema-version")
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = ""
    groups: tuple[GovernanceSubjectGroupDefinition, ...] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _supported_schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported subject-group profile schema-version; expected 1")
        return value

    @field_validator("id", "version", "description", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("subject-group profile id must use lower-case kebab-case")
        return value

    @model_validator(mode="after")
    def _groups_are_unique(self) -> GovernanceSubjectGroupProfile:
        ids = tuple(group.id for group in self.groups)
        if len(ids) != len(set(ids)):
            raise ValueError("subject-group ids must be unique")
        return self

    def group(self, group_id: str) -> GovernanceSubjectGroupDefinition | None:
        """Return one group by its stable identifier."""

        return next((group for group in self.groups if group.id == group_id), None)
