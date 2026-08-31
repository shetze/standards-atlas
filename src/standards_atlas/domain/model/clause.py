"""Clause model for Standards Atlas."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from standards_atlas.domain.model.content import (
    ContentBlock,
    render_content_as_plain_text,
)
from standards_atlas.domain.model.context_routing import ContextRouting
from standards_atlas.domain.model.doorstop_attributes import DoorstopItemAttributes
from standards_atlas.domain.model.identifiers import ClauseId, StandardReference
from standards_atlas.domain.model.knowledge_state import (
    GeneratedAttribute,
    KnowledgeStateProvenance,
)
from standards_atlas.domain.model.reference_mention import ReferenceMention
from standards_atlas.domain.model.semantic_classification import (
    DocumentStructureClassification,
    NormativeStatus,
    SemanticClassification,
    SemanticRelation,
)
from standards_atlas.domain.model.structural_context import StructuralContext
from standards_atlas.domain.model.structural_profile import StructuralProfile
from standards_atlas.domain.model.subject_context import (
    ClauseSubjectContext,
    PrimarySubjectContext,
)


class ClauseType(StrEnum):
    """Semantic type of a clause-like standard item."""

    TOC = "toc"
    CLAUSE = "clause"
    REQUIREMENT = "requirement"
    SCOPE = "scope"
    TERM = "term"
    OBJECTIVE = "objective"
    TABLE = "table"
    MISC = "misc"


class ClauseBaseline(BaseModel):
    """Source-derived and deterministic knowledge for one clause.

    Baseline does not mean infallible. Algorithmically detected properties stay
    in this block but are listed in :class:`KnowledgeStateProvenance` until
    confirmed by an authoritative source such as curated AtlasData.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    heading: str | None = None
    content: tuple[ContentBlock, ...] = ()
    parent_id: ClauseId | None = None
    source_token: str | None = None
    enum_prefix: str | None = None
    identifier_width: int | None = None
    doorstop: DoorstopItemAttributes | None = None

    structural_profile: StructuralProfile | None = None
    structural_context: StructuralContext | None = None
    reference_mentions: tuple[ReferenceMention, ...] = ()
    document_structure: DocumentStructureClassification | None = None
    normative_status: NormativeStatus = NormativeStatus.UNSPECIFIED
    reference_relations: tuple[SemanticRelation, ...] = ()


class ClauseEnrichments(BaseModel):
    """Interpretative and model-assisted knowledge derived for one clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    semantic: SemanticClassification = SemanticClassification()
    context_routing: ContextRouting = ContextRouting()
    subject_context: ClauseSubjectContext = ClauseSubjectContext()


class Clause(BaseModel):
    """A clause-like item in the canonical engineering knowledge state.

    Identity belongs directly to the clause. Source-derived and deterministic
    facts are grouped under :attr:`baseline`; interpretative results are under
    :attr:`enrichments`. Attribute-level authority is tracked separately in
    :attr:`provenance`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: ClauseId
    reference: StandardReference
    clause_type: ClauseType
    baseline: ClauseBaseline = ClauseBaseline()
    enrichments: ClauseEnrichments = ClauseEnrichments()
    provenance: KnowledgeStateProvenance = KnowledgeStateProvenance()

    @model_validator(mode="before")
    @classmethod
    def normalize_constructor_shape(cls, data: Any) -> Any:
        """Normalize in-process flat construction to the canonical nested shape.

        Persisted EngineeringDocument schema v8 only writes the nested shape.
        This normalizer keeps Python construction concise while the refactoring
        migrates call sites; it is not a reader compatibility promise for older
        persisted schema versions.
        """
        if not isinstance(data, dict) or "baseline" in data or "enrichments" in data:
            return data
        payload = dict(data)
        baseline_fields = set(ClauseBaseline.model_fields)
        baseline = {name: payload.pop(name) for name in tuple(payload) if name in baseline_fields}
        semantic = payload.pop("semantic_classification", None)
        if semantic is not None:
            # document_structure, normative_status and deterministic relations are baseline facts.
            if isinstance(semantic, SemanticClassification):
                baseline.setdefault("document_structure", semantic.document_structure)
                baseline.setdefault("normative_status", semantic.normative_status)
                semantic = semantic.model_copy(
                    update={
                        "document_structure": None,
                        "normative_status": NormativeStatus.UNSPECIFIED,
                    }
                )
            payload["enrichments"] = {"semantic": semantic}
        payload["baseline"] = baseline
        return payload

    @property
    def semantic_classification(self) -> SemanticClassification:
        """Return derived semantic enrichment (read-only convenience projection)."""
        return self.enrichments.semantic

    @property
    def context_routing(self) -> ContextRouting:
        """Return derived CBox routing enrichment (read-only convenience projection)."""
        return self.enrichments.context_routing

    @property
    def primary_subject(self) -> PrimarySubjectContext | None:
        """Return the deterministic primary subject when one is available."""
        return self.enrichments.subject_context.primary_subject

    @property
    def subject_context(self) -> ClauseSubjectContext:
        """Return deterministic subject-oriented CBox enrichment."""
        return self.enrichments.subject_context

    @property
    def structural_profile(self) -> StructuralProfile | None:
        return self.baseline.structural_profile

    @property
    def structural_context(self) -> StructuralContext | None:
        return self.baseline.structural_context

    @property
    def document_structure(self) -> DocumentStructureClassification | None:
        return self.baseline.document_structure

    @property
    def normative_status(self) -> NormativeStatus:
        return self.baseline.normative_status

    @property
    def reference_mentions(self) -> tuple[ReferenceMention, ...]:
        return self.baseline.reference_mentions

    @property
    def reference_relations(self) -> tuple[SemanticRelation, ...]:
        return self.baseline.reference_relations

    @property
    def heading(self) -> str | None:
        return self.baseline.heading

    @property
    def content(self) -> tuple[ContentBlock, ...]:
        return self.baseline.content

    @property
    def parent_id(self) -> ClauseId | None:
        return self.baseline.parent_id

    @property
    def source_token(self) -> str | None:
        return self.baseline.source_token

    @property
    def enum_prefix(self) -> str | None:
        return self.baseline.enum_prefix

    @property
    def identifier_width(self) -> int | None:
        return self.baseline.identifier_width

    @property
    def doorstop(self) -> DoorstopItemAttributes | None:
        return self.baseline.doorstop

    @property
    def plain_text(self) -> str:
        """Return a stable plain-text projection of structured content."""
        return render_content_as_plain_text(self.baseline.content)

    def with_baseline_updates(self, **updates: object) -> Clause:
        """Return a clause with deterministic/source-derived baseline updates."""
        return self.model_copy(update={"baseline": self.baseline.model_copy(update=updates)})

    def with_semantic_classification(self, semantic: SemanticClassification) -> Clause:
        """Return a clause with a replaced semantic enrichment."""
        return self.model_copy(
            update={"enrichments": self.enrichments.model_copy(update={"semantic": semantic})}
        )

    def with_context_routing(self, routing: ContextRouting) -> Clause:
        """Return a clause with replaced contextual routing enrichment."""
        return self.model_copy(
            update={"enrichments": self.enrichments.model_copy(update={"context_routing": routing})}
        )

    def with_subject_context(self, subject_context: ClauseSubjectContext) -> Clause:
        """Return a clause with replaced deterministic subject context."""
        return self.model_copy(
            update={
                "enrichments": self.enrichments.model_copy(
                    update={"subject_context": subject_context}
                )
            }
        )

    def mark_generated(self, *attributes: GeneratedAttribute) -> Clause:
        """Return a clause with generated attribute provenance upserted by path."""
        return self.model_copy(update={"provenance": self.provenance.mark_generated(*attributes)})

    def confirm_authoritative(self, *paths: str) -> Clause:
        """Return a clause after authoritative confirmation of generated paths."""
        return self.model_copy(update={"provenance": self.provenance.confirm_authoritative(*paths)})
