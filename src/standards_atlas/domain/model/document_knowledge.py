"""Accepted assertion-centred engineering knowledge for one document."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from standards_atlas.domain.model.identifiers import ClauseId

DOCUMENT_KNOWLEDGE_SCHEMA_VERSION = 1
_IRI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")


def _require_absolute_iri(value: str, *, field_name: str) -> str:
    """Reject local names and other values that cannot identify ontology terms globally."""
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    scheme = urlsplit(value).scheme
    if not scheme or not _IRI_SCHEME.fullmatch(scheme):
        raise ValueError(f"{field_name} must be an absolute IRI")
    return value


class NormativeForce(StrEnum):
    """Normative force attached to one extracted engineering assertion."""

    REQUIREMENT = "requirement"
    RECOMMENDATION = "recommendation"
    PERMISSION = "permission"
    PROHIBITION = "prohibition"
    INFORMATIVE = "informative"
    UNSPECIFIED = "unspecified"


class KnowledgeDerivationMethod(StrEnum):
    """How accepted canonical knowledge was produced before adoption."""

    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"
    HUMAN_AUTHORED = "human_authored"
    IMPORTED = "imported"


class KnowledgeProvenance(BaseModel):
    """Audit metadata for accepted document knowledge.

    The provenance records how a proposal was produced and, where applicable,
    which qualification or review evidence justified adoption. It is not itself a
    claim that model-generated knowledge is authoritative.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: KnowledgeDerivationMethod
    producer: str = Field(min_length=1)
    producer_version: str | None = None
    qualification_reference: str | None = None
    review_reference: str | None = None
    input_hash: str | None = None


class EvidenceSourceKind(StrEnum):
    """Canonical clause surface addressed by one evidence anchor."""

    BODY = "body"
    HEADING = "heading"


class EvidenceAnchor(BaseModel):
    """Text-safe anchor from engineering knowledge back to one canonical clause surface.

    The value object can be carried by a non-canonical proposal or by accepted
    ``DocumentKnowledge``. Authority comes from the containing aggregate, not from
    the anchor itself. ``source_clause_id`` identifies the clause that owns the evidence
    surface and ``source_kind`` selects either its canonical body projection or heading.
    Character offsets are relative to that selected surface. If offsets are omitted, the
    complete selected surface is the evidence scope. Protected source text is never copied
    into the anchor.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    source_clause_id: ClauseId
    source_kind: EvidenceSourceKind
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def offsets_form_a_valid_range(self) -> EvidenceAnchor:
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("evidence anchor offsets must be supplied together")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset <= self.start_offset
        ):
            raise ValueError("evidence anchor end_offset must be greater than start_offset")
        return self


class KnowledgeEntity(BaseModel):
    """Normalized engineering entity mentioned by one canonical document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    class_iri: str = Field(min_length=1)
    normalized_label: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    source_anchor_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("class_iri")
    @classmethod
    def class_iri_is_absolute(cls, value: str) -> str:
        return _require_absolute_iri(value, field_name="knowledge entity class_iri")

    @model_validator(mode="after")
    def aliases_and_anchors_are_unique(self) -> KnowledgeEntity:
        if len(self.aliases) != len(set(self.aliases)):
            raise ValueError("knowledge entity aliases must be unique")
        if len(self.source_anchor_ids) != len(set(self.source_anchor_ids)):
            raise ValueError("knowledge entity source anchors must be unique")
        return self


class EntityAssertionObject(BaseModel):
    """Assertion object referencing another normalized entity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["entity"] = "entity"
    entity_id: str = Field(min_length=1)


class LiteralAssertionObject(BaseModel):
    """Literal assertion object independent from RDF serialization details."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["literal"] = "literal"
    value: str | int | float | bool
    datatype_iri: str | None = None
    language: str | None = None

    @model_validator(mode="after")
    def datatype_and_language_are_mutually_exclusive(self) -> LiteralAssertionObject:
        if self.datatype_iri and self.language:
            raise ValueError("literal assertion objects cannot define datatype and language")
        return self


AssertionObject = Annotated[
    EntityAssertionObject | LiteralAssertionObject,
    Field(discriminator="kind"),
]


class NormativeAssertion(BaseModel):
    """One evidence-backed engineering statement made by a source clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    source_clause_id: ClauseId
    subject_id: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: AssertionObject
    normative_force: NormativeForce = NormativeForce.UNSPECIFIED
    evidence_anchor_ids: tuple[str, ...] = Field(min_length=1)
    provenance: KnowledgeProvenance

    @field_validator("predicate")
    @classmethod
    def predicate_is_absolute(cls, value: str) -> str:
        return _require_absolute_iri(value, field_name="normative assertion predicate")

    @model_validator(mode="after")
    def evidence_anchors_are_unique(self) -> NormativeAssertion:
        if len(self.evidence_anchor_ids) != len(set(self.evidence_anchor_ids)):
            raise ValueError("normative assertion evidence anchors must be unique")
        return self


class DocumentKnowledge(BaseModel):
    """Accepted engineering knowledge owned by one EngineeringDocument.

    Proposal runs, disagreements and rejected candidates stay outside this model.
    The aggregate contains only adopted entities/assertions plus text-safe source
    anchors, so formal graph projections remain rebuildable consumers. Semantic
    terms are bound to the exact formal ontology versions used for adoption.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = DOCUMENT_KNOWLEDGE_SCHEMA_VERSION
    ontology_versions: tuple[str, ...] = ()
    evidence_anchors: tuple[EvidenceAnchor, ...] = ()
    entities: tuple[KnowledgeEntity, ...] = ()
    assertions: tuple[NormativeAssertion, ...] = ()

    @field_validator("schema_version", mode="before")
    @classmethod
    def schema_marker_is_exact_integer_one(cls, value: object) -> object:
        if type(value) is not int or value != DOCUMENT_KNOWLEDGE_SCHEMA_VERSION:
            raise ValueError(
                "unsupported document knowledge schema version: "
                f"{value!r}; current is {DOCUMENT_KNOWLEDGE_SCHEMA_VERSION}"
            )
        return value

    @field_validator("ontology_versions")
    @classmethod
    def ontology_versions_are_explicit_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("document knowledge ontology versions must be unique")
        for reference in value:
            if reference != reference.strip() or reference.count("@") != 1:
                raise ValueError(
                    "document knowledge ontology versions must use '<id>@<version>' references"
                )
            ontology_id, version = reference.rsplit("@", 1)
            if (
                not ontology_id
                or not version
                or any(part.strip() != part for part in (ontology_id, version))
            ):
                raise ValueError(
                    "document knowledge ontology versions must use '<id>@<version>' references"
                )
        return value

    @model_validator(mode="after")
    def references_are_local_and_resolved(self) -> DocumentKnowledge:
        if (self.entities or self.assertions) and not self.ontology_versions:
            raise ValueError("document knowledge with semantic terms requires ontology_versions")

        anchor_ids = [anchor.id for anchor in self.evidence_anchors]
        entity_ids = [entity.id for entity in self.entities]
        assertion_ids = [assertion.id for assertion in self.assertions]
        for label, values in (
            ("evidence anchor", anchor_ids),
            ("knowledge entity", entity_ids),
            ("normative assertion", assertion_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} ids must be unique")

        known_anchors = set(anchor_ids)
        known_entities = set(entity_ids)
        missing_entity_anchors = {
            anchor_id
            for entity in self.entities
            for anchor_id in entity.source_anchor_ids
            if anchor_id not in known_anchors
        }
        if missing_entity_anchors:
            raise ValueError(
                "knowledge entities reference unknown evidence anchors: "
                f"{sorted(missing_entity_anchors)!r}"
            )

        missing_assertion_anchors = {
            anchor_id
            for assertion in self.assertions
            for anchor_id in assertion.evidence_anchor_ids
            if anchor_id not in known_anchors
        }
        if missing_assertion_anchors:
            raise ValueError(
                "normative assertions reference unknown evidence anchors: "
                f"{sorted(missing_assertion_anchors)!r}"
            )

        missing_subjects = {
            assertion.subject_id
            for assertion in self.assertions
            if assertion.subject_id not in known_entities
        }
        if missing_subjects:
            raise ValueError(
                f"normative assertions reference unknown subjects: {sorted(missing_subjects)!r}"
            )

        missing_objects = {
            assertion.object.entity_id
            for assertion in self.assertions
            if isinstance(assertion.object, EntityAssertionObject)
            and assertion.object.entity_id not in known_entities
        }
        if missing_objects:
            raise ValueError(
                f"normative assertions reference unknown objects: {sorted(missing_objects)!r}"
            )
        return self
