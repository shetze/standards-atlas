"""Deterministic classification of document-independent structural dimensions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from standards_atlas.domain.model.structural_profile import (
    AnnexStatus,
    CanonicalDocumentSection,
    DomainCategory,
    SemanticSection,
    SemanticSectionRole,
    StructuralProfile,
)


@dataclass(frozen=True)
class StructuralProfileContext:
    """Context required for conservative structural classification."""

    reference: str
    heading: str
    text: str = ""
    document_taxonomy: str | None = None
    document_category: str | None = None
    document_taxonomy_version: str | None = None
    domain_taxonomy: str | None = None
    domain_category: str | None = None
    domain_taxonomy_version: str | None = None


class StructuralProfileClassifier:
    """Build a profile without assuming an IEC-style document structure."""

    def classify(self, context: StructuralProfileContext) -> StructuralProfile:
        heading = _normalize_heading(context.heading)
        canonical_section = _canonical_section(context.reference, heading)
        annex_status = (
            _annex_status(heading) if canonical_section == CanonicalDocumentSection.ANNEX else None
        )

        document_categories = _qualified_category(
            context.document_taxonomy,
            context.document_category,
            context.document_taxonomy_version,
        )
        domain_categories = _qualified_category(
            context.domain_taxonomy,
            context.domain_category,
            context.domain_taxonomy_version,
        )
        return StructuralProfile(
            canonical_section=canonical_section,
            document_categories=document_categories,
            domain_categories=domain_categories,
            annex_status=annex_status,
            semantic_sections=_semantic_sections(context.text),
        )


def _qualified_category(
    taxonomy: str | None,
    category: str | None,
    version: str | None,
) -> tuple[DomainCategory, ...]:
    if taxonomy is None or category is None:
        return ()
    return (DomainCategory(taxonomy=taxonomy, category=category, version=version),)


def _canonical_section(reference: str, heading: str) -> CanonicalDocumentSection | None:
    if _is_annex(reference, heading):
        return CanonicalDocumentSection.ANNEX
    exact = {
        "foreword": CanonicalDocumentSection.FRONT_MATTER,
        "introduction": CanonicalDocumentSection.INTRODUCTION,
        "scope": CanonicalDocumentSection.SCOPE,
        "normative references": CanonicalDocumentSection.REFERENCES,
        "references": CanonicalDocumentSection.REFERENCES,
        "terms and definitions": CanonicalDocumentSection.TERMINOLOGY,
        "terms, definitions and abbreviated terms": CanonicalDocumentSection.TERMINOLOGY,
        "bibliography": CanonicalDocumentSection.BIBLIOGRAPHY,
    }
    matched = exact.get(heading.casefold())
    if matched is not None:
        return matched
    if re.fullmatch(r"[1-9]\d*(?:\.\d+)*", reference.strip()):
        return CanonicalDocumentSection.BODY
    return None


def _annex_status(heading: str) -> AnnexStatus:
    match = re.search(r"\((normative|informative)\)", heading, re.I)
    if match is None:
        return AnnexStatus.UNSPECIFIED
    return AnnexStatus(match.group(1).lower())


def _is_annex(reference: str, heading: str) -> bool:
    return bool(
        re.fullmatch(r"[A-Z]{1,2}(?:\.\d+)*", reference)
        or re.match(r"^annex\s+[A-Z]{1,2}\b", heading, re.I)
    )


def _normalize_heading(value: str) -> str:
    heading = re.sub(r"\s+", " ", value).strip()
    return re.sub(
        r"^(?:0\.\d+(?:\.\d+)*|[1-9]\d*(?:\.\d+)*|[A-Z](?:\.\d+)*)\s+",
        "",
        heading,
    ).strip(" :-")


_SECTION_LABEL_PATTERN = re.compile(
    r"(?im)(?:^|(?<=\n)|(?<=\r)|(?<=[.;]))[ \t]*"
    r"(?P<label>aim|objective|description|references?|rationale|examples?|notes?|"
    r"inputs?|outputs?|prerequisites?)[ \t]*:[ \t]*"
)

_SECTION_ROLES = {
    "aim": SemanticSectionRole.AIM,
    "objective": SemanticSectionRole.AIM,
    "description": SemanticSectionRole.DESCRIPTION,
    "reference": SemanticSectionRole.REFERENCES,
    "references": SemanticSectionRole.REFERENCES,
    "rationale": SemanticSectionRole.RATIONALE,
    "example": SemanticSectionRole.EXAMPLE,
    "examples": SemanticSectionRole.EXAMPLE,
    "note": SemanticSectionRole.NOTE,
    "notes": SemanticSectionRole.NOTE,
    "input": SemanticSectionRole.INPUTS,
    "inputs": SemanticSectionRole.INPUTS,
    "output": SemanticSectionRole.OUTPUTS,
    "outputs": SemanticSectionRole.OUTPUTS,
    "prerequisite": SemanticSectionRole.PREREQUISITES,
    "prerequisites": SemanticSectionRole.PREREQUISITES,
}


def _semantic_sections(text: str) -> tuple[SemanticSection, ...]:
    """Locate explicit labelled content sections without duplicating clause text."""

    if not text.strip():
        return ()
    matches = list(_SECTION_LABEL_PATTERN.finditer(text))
    sections: list[SemanticSection] = []
    for index, match in enumerate(matches):
        label = match.group("label")
        start = match.start("label")
        end = matches[index + 1].start("label") if index + 1 < len(matches) else len(text)
        sections.append(
            SemanticSection(
                label=label,
                role=_SECTION_ROLES.get(label.casefold()),
                start_offset=start,
                end_offset=end,
            )
        )
    return tuple(sections)
