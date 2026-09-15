"""Metadata contract for versioned formal ontology resources."""

from __future__ import annotations

import re
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.domain.model import FORMAL_SEMANTIC_NAMESPACE, FORMAL_SEMANTIC_PREFIX

_LOCAL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class FormalOntologyExtractionVocabulary(BaseModel):
    """Explicit ontology terms that may be populated from source text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    classes: tuple[str, ...] = ()
    properties: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_local_names(self) -> FormalOntologyExtractionVocabulary:
        for kind, values in (("class", self.classes), ("property", self.properties)):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate extraction {kind} term")
            for value in values:
                if not _LOCAL_NAME.fullmatch(value):
                    raise ValueError(f"invalid extraction {kind} local name: {value!r}")
        return self


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
    extraction_vocabulary: FormalOntologyExtractionVocabulary = Field(
        default_factory=FormalOntologyExtractionVocabulary
    )

    @model_validator(mode="after")
    def stable_namespace_is_required(self) -> FormalOntologyDefinition:
        if self.namespace != FORMAL_SEMANTIC_NAMESPACE or self.prefix != FORMAL_SEMANTIC_PREFIX:
            raise ValueError("formal ontologies must use the canonical stat namespace and prefix")
        return self
