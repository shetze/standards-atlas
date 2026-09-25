"""Generic engineering document model."""

from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.domain.model.annotation import ClauseAnnotation
from standards_atlas.domain.model.artifact_lineage import ArtifactLineage
from standards_atlas.domain.model.clause import Clause
from standards_atlas.domain.model.document_knowledge import (
    DocumentKnowledge,
    EvidenceSourceKind,
)
from standards_atlas.domain.model.identifiers import ClauseId, DocumentKey
from standards_atlas.domain.model.table_structure import DocumentTable, TableIndexEntry


class DocumentType(StrEnum):
    """Type of engineering document."""

    STANDARD = "standard"
    SPECIFICATION = "specification"
    REPORT = "report"
    SAFETY_CASE_ARTIFACT = "safety_case_artifact"
    OTHER = "other"


class EngineeringDocument(BaseModel):
    """Generic structured engineering document.

    This model is intentionally broader than a standard. It can represent
    standards, specifications, reports, safety case artifacts, and other
    structured engineering documents.

    The document structure is represented through Clause objects. For
    non-standard documents, clause references may be virtual identifiers
    derived from document headings, table rows, or adapter-specific structure.
    """

    model_config = ConfigDict(frozen=True)

    key: DocumentKey
    title: str = Field(min_length=1)
    document_type: DocumentType

    year: int | None = None
    version: str | None = None
    source: str | None = None

    clauses: tuple[Clause, ...] = ()
    tables: tuple[DocumentTable, ...] = ()
    table_index: tuple[TableIndexEntry, ...] = ()
    annotations: tuple[ClauseAnnotation, ...] = ()
    knowledge: DocumentKnowledge = DocumentKnowledge()
    lineage: ArtifactLineage | None = None

    @model_validator(mode="after")
    def knowledge_is_bound_to_document_clauses(self) -> EngineeringDocument:
        """Require every accepted knowledge anchor to resolve inside this document."""
        clauses = {clause.id.value: clause for clause in self.clauses}
        for assertion in self.knowledge.assertions:
            if assertion.source_clause_id.value not in clauses:
                raise ValueError(
                    f"document knowledge assertion {assertion.id!r} references unknown source "
                    f"clause {assertion.source_clause_id.value!r}"
                )
        for anchor in self.knowledge.evidence_anchors:
            clause = clauses.get(anchor.source_clause_id.value)
            if clause is None:
                raise ValueError(
                    f"document knowledge anchor {anchor.id!r} references unknown clause "
                    f"{anchor.source_clause_id.value!r}"
                )
            if anchor.source_kind is EvidenceSourceKind.BODY:
                source_text = clause.plain_text
                source_name = "clause body"
            else:
                source_text = clause.heading
                source_name = "clause heading"
                if source_text is None:
                    raise ValueError(
                        f"document knowledge anchor {anchor.id!r} references a missing "
                        "clause heading"
                    )
            if anchor.start_offset is None:
                evidence_text = source_text
            else:
                assert anchor.end_offset is not None
                if anchor.end_offset > len(source_text):
                    raise ValueError(
                        f"document knowledge anchor {anchor.id!r} exceeds {source_name} length"
                    )
                evidence_text = source_text[anchor.start_offset : anchor.end_offset]
            if anchor.content_hash is not None:
                actual_hash = hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()
                if actual_hash != anchor.content_hash:
                    raise ValueError(
                        f"document knowledge anchor {anchor.id!r} content hash does not match"
                    )
        return self

    def annotations_for_clause(
        self,
        clause_id: ClauseId,
    ) -> tuple[ClauseAnnotation, ...]:
        """Return all annotations associated with a clause."""
        return tuple(
            annotation for annotation in self.annotations if annotation.clause_id == clause_id
        )
