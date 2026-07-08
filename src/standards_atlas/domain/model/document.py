"""Generic engineering document model."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.domain.model.clause import Clause
from standards_atlas.domain.model.identifiers import DocumentKey


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
