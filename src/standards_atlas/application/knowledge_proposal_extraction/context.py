"""Compact canonical CBox projection for assertion extraction and review."""

from __future__ import annotations

from standards_atlas.application.context.canonical_cbox import (
    CBOX_CONTRACT_VERSION,
    project_clause_enrichments,
)
from standards_atlas.domain.model import Clause, ClauseApplicability, EngineeringDocument


def assertion_cbox_context(
    document: EngineeringDocument,
    clause: Clause,
    *,
    applicability: ClauseApplicability | None = None,
) -> dict[str, object]:
    """Return the deterministic context shared by extractor, verifier and HITL review.

    The projection intentionally carries document structure and accepted CBox enrichments
    without copying clause prose.  It is small enough for the LLM request but preserves the
    parent/ancestor, sibling and interpreted-reference context that can change the meaning of
    otherwise isolated subclauses.
    """

    profile = clause.structural_profile
    structural_context = (
        clause.structural_context.model_dump(mode="json")
        if clause.structural_context is not None
        else None
    )
    enrichments = project_clause_enrichments(clause)
    enrichment_by_path = {item.path: item for item in enrichments.attributes}

    def known_value(path: str) -> object | None:
        item = enrichment_by_path.get(path)
        return item.value if item is not None and item.availability == "known" else None

    resolved_applicability: object = (
        applicability.model_dump(mode="json")
        if applicability is not None
        else known_value("enrichments.applicability")
    )

    return {
        "canonical_cbox_version": CBOX_CONTRACT_VERSION,
        "document_key": document.key.value,
        "clause_id": clause.id.value,
        "reference": clause.reference.clause,
        "heading": clause.heading,
        "parent_id": clause.parent_id.value if clause.parent_id is not None else None,
        "ancestor_headings": _ancestor_headings(document, clause),
        "normative_status": clause.normative_status.value,
        "clause_type": clause.clause_type.value,
        "canonical_section": profile.canonical_section.value if profile else None,
        "document_categories": (
            [item.model_dump(mode="json") for item in profile.document_categories]
            if profile is not None
            else []
        ),
        "domain_categories": (
            [item.model_dump(mode="json") for item in profile.domain_categories]
            if profile is not None
            else []
        ),
        "semantic_sections": (
            [item.model_dump(mode="json") for item in profile.semantic_sections]
            if profile is not None
            else []
        ),
        "structural_context": structural_context,
        "reference_mentions": [item.model_dump(mode="json") for item in clause.reference_mentions],
        "reference_relations": [
            item.model_dump(mode="json") for item in clause.reference_relations
        ],
        "context_routing": known_value("enrichments.context_routing"),
        "subject_context": known_value("enrichments.subject_context"),
        "primary_subject": (
            clause.primary_subject.normalized_label if clause.primary_subject is not None else None
        ),
        "applicability": resolved_applicability,
        "attribute_sources": {
            item.path: item.model_dump(mode="json", exclude={"value"})
            for item in enrichments.attributes
        },
    }


def _ancestor_headings(document: EngineeringDocument, clause: Clause) -> list[dict[str, str]]:
    """Return nearest-first parent headings from the current EngineeringDocument."""

    by_id = {item.id.value: item for item in document.clauses}
    parent_id = clause.parent_id.value if clause.parent_id is not None else None
    seen = {clause.id.value}
    headings: list[dict[str, str]] = []
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = by_id.get(parent_id)
        if parent is None:
            break
        if parent.heading and parent.heading.strip():
            headings.append(
                {
                    "clause_id": parent.id.value,
                    "reference": parent.reference.clause,
                    "heading": parent.heading.strip(),
                }
            )
        parent_id = parent.parent_id.value if parent.parent_id is not None else None
    return headings
