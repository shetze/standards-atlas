"""Multi-dimensional structural classification for engineering documents."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CanonicalDocumentSection(StrEnum):
    """Broad document section independent of a particular knowledge domain.

    The vocabulary deliberately stops at categories shared by multiple document
    families. It does not assume that every document has a normative main body,
    verification section, management section, or any other standards-specific
    structure.
    """

    FRONT_MATTER = "front_matter"
    INTRODUCTION = "introduction"
    SCOPE = "scope"
    REFERENCES = "references"
    TERMINOLOGY = "terminology"
    BODY = "body"
    ANNEX = "annex"
    BIBLIOGRAPHY = "bibliography"
    BACK_MATTER = "back_matter"


class AnnexStatus(StrEnum):
    """Normative force explicitly assigned to an annex."""

    NORMATIVE = "normative"
    INFORMATIVE = "informative"
    UNSPECIFIED = "unspecified"


class SemanticSectionRole(StrEnum):
    """Canonical role of an explicitly labelled subsection within clause content."""

    AIM = "aim"
    DESCRIPTION = "description"
    REFERENCES = "references"
    RATIONALE = "rationale"
    EXAMPLE = "example"
    NOTE = "note"
    INPUTS = "inputs"
    OUTPUTS = "outputs"
    PREREQUISITES = "prerequisites"


class SemanticSection(BaseModel):
    """Location of an explicitly labelled semantic subsection in clause plain text.

    Text is not duplicated here. ``start_offset`` and ``end_offset`` address the
    corresponding slice of the clause's canonical plain-text projection.
    ``role`` is intentionally optional so document-family-specific labels can be
    preserved without extending a central enum.
    """

    model_config = ConfigDict(frozen=True)

    label: str = Field(min_length=1)
    role: SemanticSectionRole | None = None
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> SemanticSection:
        if self.end_offset <= self.start_offset:
            raise ValueError("semantic section end_offset must be greater than start_offset")
        return self


class DomainCategory(BaseModel):
    """Category owned by a versioned, domain-specific taxonomy."""

    model_config = ConfigDict(frozen=True)

    taxonomy: str = Field(min_length=1)
    category: str = Field(min_length=1)
    version: str | None = None


class StructuralProfile(BaseModel):
    """Independent structural dimensions assigned to one clause.

    ``canonical_section`` supports broad comparison across document families.
    ``document_categories`` describe structure specific to a document family,
    such as a Polarion work-item type or a TSI chapter family.
    ``domain_categories`` describe knowledge-domain semantics, such as a phase
    in a Functional Safety lifecycle. Both category collections are open and
    namespaced so new document types and KnowledgeDomains do not require a
    central enum change.
    """

    model_config = ConfigDict(frozen=True)

    canonical_section: CanonicalDocumentSection | None = None
    document_categories: tuple[DomainCategory, ...] = ()
    domain_categories: tuple[DomainCategory, ...] = ()
    annex_status: AnnexStatus | None = None
    semantic_sections: tuple[SemanticSection, ...] = ()

    @model_validator(mode="after")
    def validate_annex_status(self) -> StructuralProfile:
        if (
            self.annex_status is not None
            and self.canonical_section != CanonicalDocumentSection.ANNEX
        ):
            raise ValueError("annex_status requires canonical_section='annex'")
        return self
