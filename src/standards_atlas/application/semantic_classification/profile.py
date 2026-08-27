"""Semantic profile contracts for multidimensional clause classification."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.ontology.definition import OntologyReference


class SemanticProfile(BaseModel):
    """Composition of ontology dimensions used by one semantic classification task."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    dimensions: dict[str, OntologyReference] = Field(min_length=1)

    @model_validator(mode="after")
    def _dimension_names_are_non_empty(self) -> SemanticProfile:
        if any(not dimension.strip() for dimension in self.dimensions):
            raise ValueError("semantic profile dimension names must be non-empty")
        return self
