"""Compact canonical CBox projection for assertion extraction and review."""

from __future__ import annotations

from standards_atlas.application.context.canonical_cbox import project_clause_enrichments
from standards_atlas.application.context.normative_context import (
    governing_scope_context,
    resolve_normative_context,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseApplicability,
    ClauseType,
    EngineeringDocument,
)

ASSERTION_CBOX_CONTRACT_VERSION = "1.3"


def assertion_cbox_context(
    document: EngineeringDocument,
    clause: Clause,
    *,
    applicability: ClauseApplicability | None = None,
) -> dict[str, object]:
    """Return the deterministic context shared by extractor, verifier and HITL review.

    The projection carries document structure, accepted CBox enrichments and a bounded set of
    source-backed associative prose needed to interpret otherwise isolated subclauses. It keeps
    governing scope separate from structural framing so contextual content cannot silently become
    a normative assertion.
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

    governing_scopes = governing_scope_context(document, clause)
    normative_context = resolve_normative_context(
        document, clause, governing_scopes=governing_scopes
    )

    resolved_applicability: object = (
        applicability.model_dump(mode="json")
        if applicability is not None
        else known_value("enrichments.applicability")
    )

    return {
        "canonical_cbox_version": ASSERTION_CBOX_CONTRACT_VERSION,
        "document_key": document.key.value,
        "document_title": document.title,
        "clause_id": clause.id.value,
        "reference": clause.reference.clause,
        "heading": clause.heading,
        "parent_id": clause.parent_id.value if clause.parent_id is not None else None,
        "ancestor_headings": _ancestor_headings(document, clause),
        "associative_context": _associative_context(document, clause),
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
        "governing_scopes": list(governing_scopes),
        "normative_context": normative_context,
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


def _associative_context(
    document: EngineeringDocument,
    clause: Clause,
) -> list[dict[str, object]]:
    """Return source-backed structural context that may frame entity semantics.

    Text-bearing ancestors are carried directly. When the *immediate structural parent*
    has no own body, the first substantive descendant before the current clause is used as
    the leading associative context for that sibling group. More distant heading-only
    ancestors do not contribute an arbitrary descendant from another branch. The projection
    is deterministic and deliberately distinct from governing scope: it may frame entities
    and retrieval, but it does not propagate normative assertions.
    """

    positions = {item.id.value: index for index, item in enumerate(document.clauses)}
    children: dict[str | None, list[Clause]] = {}
    for item in document.clauses:
        parent_id = item.parent_id.value if item.parent_id is not None else None
        children.setdefault(parent_id, []).append(item)

    entries: list[dict[str, object]] = []
    seen_sources: set[str] = set()
    current_position = positions.get(clause.id.value, -1)
    ancestors = _ancestor_clauses_nearest_first(document, clause)
    if not ancestors:
        return entries

    immediate_parent = ancestors[0]
    if immediate_parent.reference.clause != "0":
        if immediate_parent.plain_text.strip():
            _append_associative_context_entry(
                entries,
                seen_sources,
                source=immediate_parent,
                role="ancestor_body",
                via_ancestor=immediate_parent,
            )
        else:
            lead = _first_substantive_descendant(immediate_parent, children)
            if lead is not None and lead.id != clause.id:
                lead_position = positions.get(lead.id.value, -1)
                if (
                    lead_position >= 0
                    and current_position >= 0
                    and lead_position < current_position
                ):
                    _append_associative_context_entry(
                        entries,
                        seen_sources,
                        source=lead,
                        role="leading_substantive_descendant",
                        via_ancestor=immediate_parent,
                    )

    for ancestor in ancestors[1:]:
        if ancestor.reference.clause == "0":
            continue
        if ancestor.plain_text.strip():
            _append_associative_context_entry(
                entries,
                seen_sources,
                source=ancestor,
                role="ancestor_body",
                via_ancestor=ancestor,
            )
    return entries


def _ancestor_clauses_nearest_first(
    document: EngineeringDocument,
    clause: Clause,
) -> list[Clause]:
    by_id = {item.id.value: item for item in document.clauses}
    parent_id = clause.parent_id.value if clause.parent_id is not None else None
    seen = {clause.id.value}
    ancestors: list[Clause] = []
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = by_id.get(parent_id)
        if parent is None:
            break
        ancestors.append(parent)
        parent_id = parent.parent_id.value if parent.parent_id is not None else None
    return ancestors


def _first_substantive_descendant(
    ancestor: Clause,
    children: dict[str | None, list[Clause]],
) -> Clause | None:
    pending = list(children.get(ancestor.id.value, ()))
    while pending:
        item = pending.pop(0)
        if _is_substantive_associative_source(item):
            return item
        pending[0:0] = children.get(item.id.value, ())
    return None


def _is_substantive_associative_source(clause: Clause) -> bool:
    if clause.clause_type in {ClauseType.TOC, ClauseType.TABLE}:
        return False
    return bool(clause.plain_text.strip())


def _append_associative_context_entry(
    entries: list[dict[str, object]],
    seen_sources: set[str],
    *,
    source: Clause,
    role: str,
    via_ancestor: Clause,
) -> None:
    if source.id.value in seen_sources:
        return
    seen_sources.add(source.id.value)
    entries.append(
        {
            "clause_id": source.id.value,
            "reference": source.reference.clause,
            "heading": source.heading,
            "text": source.plain_text,
            "role": role,
            "via_ancestor_clause_id": via_ancestor.id.value,
            "via_ancestor_reference": via_ancestor.reference.clause,
            "via_ancestor_heading": via_ancestor.heading,
        }
    )
