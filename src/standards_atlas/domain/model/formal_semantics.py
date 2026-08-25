"""Provider-neutral contracts for formal semantics and contextual knowledge."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

FORMAL_SEMANTIC_NAMESPACE = "http://lunetix.org/standards-atlas#"
FORMAL_SEMANTIC_PREFIX = "stat"


class SemanticBox(StrEnum):
    """Logical partition of the formal semantic model."""

    TBOX = "tbox"
    RBOX = "rbox"
    ABOX = "abox"
    CBOX = "cbox"


class ContextKind(StrEnum):
    """Kinds of context that qualify semantic assertions."""

    SEMANTIC = "semantic"
    STRUCTURAL = "structural"
    EPISTEMIC = "epistemic"


class SemanticResource(BaseModel):
    """Stable RDF-compatible resource identifier without binding to an RDF library."""

    model_config = ConfigDict(frozen=True)

    iri: str = Field(min_length=1)

    @classmethod
    def stat(cls, local_name: str) -> SemanticResource:
        local_name = local_name.strip()
        if not local_name:
            raise ValueError("local_name must be non-empty")
        return cls(iri=f"{FORMAL_SEMANTIC_NAMESPACE}{local_name}")


class SemanticLiteral(BaseModel):
    """Provider-neutral literal value used as an assertion object."""

    model_config = ConfigDict(frozen=True)

    value: Any
    datatype_iri: str | None = None
    language: str | None = None

    @model_validator(mode="after")
    def datatype_and_language_are_mutually_exclusive(self) -> SemanticLiteral:
        if self.datatype_iri and self.language:
            raise ValueError("semantic literals cannot define both datatype_iri and language")
        return self


class ContextFacet(BaseModel):
    """One qualified piece of context derived from an existing source model."""

    model_config = ConfigDict(frozen=True)

    kind: ContextKind
    predicate: SemanticResource
    value: SemanticResource | SemanticLiteral
    source: str = Field(min_length=1)


class ContextFrame(BaseModel):
    """Reusable context frame that can qualify one or more assertions."""

    model_config = ConfigDict(frozen=True)

    id: SemanticResource
    facets: tuple[ContextFacet, ...] = ()

    @model_validator(mode="after")
    def facets_are_unique(self) -> ContextFrame:
        keys = [(facet.kind, facet.predicate.iri, repr(facet.value)) for facet in self.facets]
        if len(keys) != len(set(keys)):
            raise ValueError("context frame facets must be unique")
        return self


class FormalAssertion(BaseModel):
    """One formal statement assigned to TBox, RBox, ABox, or CBox."""

    model_config = ConfigDict(frozen=True)

    id: SemanticResource
    box: SemanticBox
    subject: SemanticResource
    predicate: SemanticResource
    object: SemanticResource | SemanticLiteral
    context_ids: tuple[SemanticResource, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def only_assertional_boxes_may_reference_context(self) -> FormalAssertion:
        if self.context_ids and self.box in {SemanticBox.TBOX, SemanticBox.RBOX}:
            raise ValueError("TBox/RBox axioms must not depend on instance context frames")
        return self


class FormalSemanticProjection(BaseModel):
    """Derived semantic projection; never replaces the canonical EngineeringDocument."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    namespace: str = FORMAL_SEMANTIC_NAMESPACE
    prefix: str = FORMAL_SEMANTIC_PREFIX
    source_document_key: str = Field(min_length=1)
    assertions: tuple[FormalAssertion, ...] = ()
    contexts: tuple[ContextFrame, ...] = ()

    @model_validator(mode="after")
    def assertion_contexts_exist(self) -> FormalSemanticProjection:
        known = {context.id.iri for context in self.contexts}
        missing = {
            context_id.iri
            for assertion in self.assertions
            for context_id in assertion.context_ids
            if context_id.iri not in known
        }
        if missing:
            raise ValueError(f"assertions reference unknown contexts: {sorted(missing)!r}")
        return self
