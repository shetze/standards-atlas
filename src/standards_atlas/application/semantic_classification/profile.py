"""Versioned semantic profile contracts for multidimensional clause semantics."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.ontology.definition import OntologyReference


class SemanticProfileReference(BaseModel):
    """Reference to one independently versioned semantic profile."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)

    def as_text(self) -> str:
        return f"{self.id}:{self.version}"


class SemanticProfile(BaseModel):
    """Versioned composition of ontology dimensions defining published semantic tags."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = ""
    dimensions: dict[str, OntologyReference] = Field(min_length=1)

    @model_validator(mode="after")
    def _dimension_names_are_non_empty(self) -> SemanticProfile:
        if any(not dimension.strip() for dimension in self.dimensions):
            raise ValueError("semantic profile dimension names must be non-empty")
        return self

    @property
    def reference(self) -> SemanticProfileReference:
        return SemanticProfileReference(id=self.id, version=self.version)

    def select_dimensions(self, dimensions: tuple[str, ...]) -> SemanticProfile:
        """Return a task-specific view while preserving the profile identity."""
        missing = [dimension for dimension in dimensions if dimension not in self.dimensions]
        if missing:
            raise ValueError(
                "semantic profile does not define dimensions: " + ", ".join(sorted(missing))
            )
        return self.model_copy(
            update={
                "dimensions": {dimension: self.dimensions[dimension] for dimension in dimensions}
            }
        )


class SemanticProfileRepository(Protocol):
    """Port for loading independently versioned semantic profiles."""

    def load(self, profile_id: str, version: str) -> SemanticProfile: ...
