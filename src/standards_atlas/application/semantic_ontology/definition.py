"""Versioned semantic ontology contracts."""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.schema.model import SchemaBoundModel


class OntologyDefinition(SchemaBoundModel):
    """One independently versioned semantic ontology dimension."""

    SCHEMA_FAMILY: ClassVar[str] = "ontology-resource"

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


class OntologyDefinitionRepository(Protocol):
    """Port for loading independently versioned ontology definitions."""

    def load(self, ontology_id: str, version: str) -> OntologyDefinition: ...
