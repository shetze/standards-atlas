"""Versioned semantic ontology contracts."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OntologyDefinition(BaseModel):
    """One independently versioned semantic ontology dimension."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    description: str = ""
    values: tuple[str, ...] = Field(min_length=1)
    semantics: dict[str, Any] = Field(default_factory=dict)
    codes: dict[str, str] = Field(default_factory=dict)


class OntologyReference(BaseModel):
    """Reference to one independently versioned ontology dimension."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class OntologyProfile(BaseModel):
    """Composition of ontology dimensions used by one domain or semantic task."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    dimensions: dict[str, OntologyReference] = Field(min_length=1)

    @model_validator(mode="after")
    def _dimension_names_are_non_empty(self) -> OntologyProfile:
        if any(not dimension.strip() for dimension in self.dimensions):
            raise ValueError("ontology profile dimension names must be non-empty")
        return self


class OntologyDefinitionRepository(Protocol):
    """Port for loading independently versioned ontology definitions."""

    def load(self, ontology_id: str, version: str) -> OntologyDefinition: ...
