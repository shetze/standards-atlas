"""Addressable knowledge-table projections derived from structured clause content."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model.source_evidence import SourceEvidence


class KnowledgeTableKind(StrEnum):
    """Known semantic table shapes."""

    GENERIC = "generic"
    TECHNIQUE_RECOMMENDATION_MATRIX = "technique_recommendation_matrix"
    WORK_PRODUCT_MATRIX = "work_product_matrix"
    RESPONSIBILITY_MATRIX = "responsibility_matrix"
    VERIFICATION_CRITERIA_MATRIX = "verification_criteria_matrix"
    TRACEABILITY_MATRIX = "traceability_matrix"
    APPLICABILITY_MATRIX = "applicability_matrix"


class KnowledgeConceptKind(StrEnum):
    """Portable concept kinds used by table-derived knowledge records."""

    SUBJECT = "subject"
    ACTIVITY = "activity"
    WORK_PRODUCT = "work_product"
    ROLE = "role"
    CRITERION = "criterion"
    SOURCE = "source"
    TARGET = "target"
    CONTEXT = "context"


class KnowledgeRelationKind(StrEnum):
    """Portable relation kinds derived conservatively from table schemas."""

    PRODUCES = "produces"
    RESPONSIBLE_FOR = "responsible_for"
    VERIFIED_BY = "verified_by"
    TRACES_TO = "traces_to"
    APPLICABLE_TO = "applicable_to"


class KnowledgeConcept(BaseModel):
    """One normalized concept with exact source-column provenance."""

    model_config = ConfigDict(frozen=True)
    id: str = Field(min_length=1)
    kind: KnowledgeConceptKind
    label: str = Field(min_length=1)
    source_column_index: int = Field(ge=0)
    source_header: str | None = None


class KnowledgeRelation(BaseModel):
    """One evidence-backed relation between concepts in the same record."""

    model_config = ConfigDict(frozen=True)
    kind: KnowledgeRelationKind
    source_concept_id: str = Field(min_length=1)
    target_concept_id: str = Field(min_length=1)


class StructuredKnowledgeRecord(BaseModel):
    """Domain-neutral semantic projection of a logical table row."""

    model_config = ConfigDict(frozen=True)
    concepts: tuple[KnowledgeConcept, ...] = ()
    relations: tuple[KnowledgeRelation, ...] = ()


class RecommendationLevel(StrEnum):
    """Normalized IEC 61508 recommendation markers."""

    HIGHLY_RECOMMENDED = "highly_recommended"
    RECOMMENDED = "recommended"
    NEUTRAL = "neutral"
    NOT_RECOMMENDED = "not_recommended"


class IntegrityLevelRecommendation(BaseModel):
    """One recommendation qualified by an integrity level."""

    model_config = ConfigDict(frozen=True)
    integrity_level: str = Field(min_length=1)
    level: RecommendationLevel
    source_column_index: int = Field(ge=0)
    source_marker: str = Field(min_length=1)


class TechniqueRecommendation(BaseModel):
    """Semantic interpretation of one IEC 61508 Annex A table row."""

    model_config = ConfigDict(frozen=True)
    local_identifier: str | None = None
    alternative_group: str | None = None
    technique: str = Field(min_length=1)
    description_references: tuple[str, ...] = ()
    recommendations: tuple[IntegrityLevelRecommendation, ...] = ()
    context_references: tuple[str, ...] = ()


class KnowledgeTableId(BaseModel):
    """Stable identifier for a table-derived knowledge artifact."""

    model_config = ConfigDict(frozen=True)
    value: str = Field(min_length=1)


class KnowledgeRecordId(BaseModel):
    """Stable identifier for one logical table row."""

    model_config = ConfigDict(frozen=True)
    value: str = Field(min_length=1)


class KnowledgeCell(BaseModel):
    """One normalized cell in a knowledge record."""

    model_config = ConfigDict(frozen=True)
    column_index: int = Field(ge=0)
    text: str
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    is_header: bool = False


class KnowledgeRecordSource(BaseModel):
    """Precise structural location of a record inside its source table."""

    model_config = ConfigDict(frozen=True)
    table_block_id: str = Field(min_length=1)
    row_index: int = Field(ge=0)
    source_evidence: tuple[SourceEvidence, ...] = ()


class KnowledgeRecord(BaseModel):
    """Addressable, lossless projection of one logical table row."""

    model_config = ConfigDict(frozen=True)
    id: KnowledgeRecordId
    table_id: KnowledgeTableId
    document_key: str = Field(min_length=1)
    parent_clause_id: str = Field(min_length=1)
    parent_clause_reference: str = Field(min_length=1)
    row_index: int = Field(ge=0)
    cells: tuple[KnowledgeCell, ...]
    is_header: bool = False
    source: KnowledgeRecordSource
    technique_recommendation: TechniqueRecommendation | None = None
    structured_knowledge: StructuredKnowledgeRecord | None = None

    @property
    def plain_text(self) -> str:
        """Return a deterministic retrieval-oriented text projection."""
        return " | ".join(cell.text for cell in self.cells)


class KnowledgeTable(BaseModel):
    """Addressable table artifact derived from a canonical ``TableBlock``."""

    model_config = ConfigDict(frozen=True)
    id: KnowledgeTableId
    document_key: str = Field(min_length=1)
    parent_clause_id: str = Field(min_length=1)
    parent_clause_reference: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    title: str | None = None
    table_block_id: str = Field(min_length=1)
    ordinal_in_clause: int = Field(ge=1)
    header_rows: tuple[tuple[str, ...], ...] = ()
    records: tuple[KnowledgeRecord, ...] = ()
    source_evidence: tuple[SourceEvidence, ...] = ()
    kind: KnowledgeTableKind = KnowledgeTableKind.GENERIC
    context_references: tuple[str, ...] = ()

    @property
    def plain_text(self) -> str:
        """Return a deterministic table-level text projection."""
        parts = [part for part in (self.reference, self.title) if part]
        parts.extend(record.plain_text for record in self.records)
        return "\n".join(parts)
