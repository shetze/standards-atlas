"""Metadata contract for versioned formal ontology resources."""

from typing import ClassVar

from pydantic import ConfigDict, Field, model_validator

from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.domain.model import FORMAL_SEMANTIC_NAMESPACE, FORMAL_SEMANTIC_PREFIX


class FormalOntologyDefinition(SchemaBoundModel):
    SCHEMA_FAMILY: ClassVar[str] = "formal-ontology-resource"

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    ontology_iri: str = Field(min_length=1)
    version_iri: str = Field(min_length=1)
    namespace: str = FORMAL_SEMANTIC_NAMESPACE
    prefix: str = FORMAL_SEMANTIC_PREFIX
    resource: str = Field(min_length=1)
    imports: tuple[str, ...] = ()

    @model_validator(mode="after")
    def stable_namespace_is_required(self) -> "FormalOntologyDefinition":
        if self.namespace != FORMAL_SEMANTIC_NAMESPACE or self.prefix != FORMAL_SEMANTIC_PREFIX:
            raise ValueError("formal ontologies must use the canonical stat namespace and prefix")
        return self
