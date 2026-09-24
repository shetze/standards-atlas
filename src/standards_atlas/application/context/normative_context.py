"""Deterministic normative context derived from canonical source/context evidence.

Standards Atlas treats standards content as normative by default.  Informative context
must be established from source-backed structural or routing evidence: explicit
normative status, governing scope qualifications, document/local headings, term
structure, or labelled informative spans such as NOTE/EXAMPLE/DESCRIPTION.
"""

from __future__ import annotations

import re
from typing import Any

from standards_atlas.application.references.resolution import reference_key
from standards_atlas.domain.model import (
    Clause,
    ClauseType,
    ContextRouting,
    EngineeringDocument,
    NormativeStatus,
    ScopeReach,
    ScopeReachKind,
    SemanticSectionRole,
)
from standards_atlas.domain.model.structural_profile import AnnexStatus, CanonicalDocumentSection

_CONTEXT_ROUTING_PATH = "enrichments.context_routing"
_DEFAULT_STATUS = NormativeStatus.NORMATIVE

_INFORMATIVE_QUALIFICATION = re.compile(
    r"\b(?:"
    r"informative\s+(?:character|nature)(?:\s+only)?|"
    r"informative\s+only|"
    r"for\s+(?:information|informational)\s+purposes?\s+only|"
    r"non[- ]normative"
    r")\b",
    re.I,
)
_NORMATIVE_QUALIFICATION = re.compile(
    r"\b(?:"
    r"normative\s+(?:character|nature)|"
    r"(?:is|are)\s+normative|"
    r"normative\s+requirements?"
    r")\b",
    re.I,
)
_EXPLICIT_NORMATIVE_SCOPE_QUALIFICATION = re.compile(
    r"\b(?:"
    r"(?:this\s+(?:document|standard|part))[^.]{0,120}\b(?:is|has)\b[^.]{0,40}\bnormative\b|"
    r"normative\s+(?:character|nature)"
    r")\b",
    re.I,
)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])(?:\s+|\n+)")
_INFORMATIVE_DOCUMENT_TITLE = re.compile(r"(?:^|[-–—:]\s*)(?:guidelines?|guidance)\b", re.I)
_INFORMATIVE_LOCAL_HEADING = re.compile(
    r"^\s*(?:guidelines?|guidance|examples?|description)\b", re.I
)
_INFORMATIVE_SECTION_ROLES = frozenset(
    {
        SemanticSectionRole.AIM,
        SemanticSectionRole.DESCRIPTION,
        SemanticSectionRole.REFERENCES,
        SemanticSectionRole.RATIONALE,
        SemanticSectionRole.EXAMPLE,
        SemanticSectionRole.NOTE,
    }
)


def governing_scope_context(
    document: EngineeringDocument,
    clause: Clause,
) -> tuple[dict[str, Any], ...]:
    """Return accepted scope declarations from other clauses that govern ``clause``.

    Scope routing is source-oriented: the declaration is stored on its source clause.
    Consumers need the inverse view.  Whole-document/part reaches are authoritative only
    when they originate in the document's structural Scope region; this prevents ordinary
    requirements that mention ``this document`` from becoming global CBox context.  Local
    clause/subtree reaches from non-Scope clauses remain valid.

    A structural Scope clause always has deterministic document reach.  If its generated
    routing is missing or failed, a minimal fallback declaration is projected from source
    structure, including any explicit informative/normative-character sentence found in
    the Scope text.
    """

    by_id = {item.id.value: item for item in document.clauses}
    governing: list[dict[str, Any]] = []
    for source in document.clauses:
        authoritative_scope = _is_authoritative_scope_source(source)
        routing = _known_context_routing(source)
        if routing is not None:
            for scope in routing.scopes:
                matching_reaches = tuple(
                    reach
                    for reach in scope.reaches
                    if _scope_reach_is_authoritative(source, reach)
                    and _scope_reaches_clause(document, clause, reach, by_id=by_id)
                )
                if not matching_reaches:
                    continue
                governing.append(
                    {
                        "source_clause_id": source.id.value,
                        "source_reference": source.reference.as_text(),
                        "source_heading": source.heading,
                        "reaches": [item.model_dump(mode="json") for item in matching_reaches],
                        "conditions": list(scope.conditions),
                        "exclusions": list(scope.exclusions),
                        "qualifications": list(scope.qualifications),
                        "evidence": list(scope.evidence),
                    }
                )

        if authoritative_scope and (routing is None or not routing.scopes):
            reach = ScopeReach(kind=ScopeReachKind.DOCUMENT, document_key=document.key.value)
            if _scope_reaches_clause(document, clause, reach, by_id=by_id):
                qualifications = _structural_scope_normative_qualifications(source.plain_text)
                governing.append(
                    {
                        "source_clause_id": source.id.value,
                        "source_reference": source.reference.as_text(),
                        "source_heading": source.heading,
                        "reaches": [reach.model_dump(mode="json")],
                        "conditions": [],
                        "exclusions": [],
                        "qualifications": list(qualifications),
                        "evidence": list(qualifications)
                        or [f"Deterministic structural Scope: {source.reference.as_text()}"],
                    }
                )
    return tuple(governing)


def resolve_normative_context(
    document: EngineeringDocument,
    clause: Clause,
    *,
    governing_scopes: tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    """Resolve assertion-oriented normative context from canonical evidence.

    ``source_status`` describes the governing source region. ``effective_status`` is the
    default force context for assertions from this clause; term definitions and explicitly
    informative local headings may therefore be informative even inside a normative source
    region.  Labelled NOTE/EXAMPLE/DESCRIPTION-style sections are represented as span-level
    informative overrides rather than changing the entire clause.
    """

    scopes = (
        governing_scopes
        if governing_scopes is not None
        else governing_scope_context(document, clause)
    )
    basis: list[dict[str, Any]] = []

    source_status = _explicit_clause_status(clause, basis)
    if source_status is None:
        source_status = _scope_status(scopes, basis)
    if source_status is None and _INFORMATIVE_DOCUMENT_TITLE.search(document.title or ""):
        source_status = NormativeStatus.INFORMATIVE
        basis.append(
            {
                "kind": "document_title",
                "status": NormativeStatus.INFORMATIVE.value,
                "value": document.title,
            }
        )
    if source_status is None:
        source_status = _DEFAULT_STATUS
        basis.append(
            {
                "kind": "default_standard_context",
                "status": _DEFAULT_STATUS.value,
                "value": "standards content is normative unless informative evidence applies",
            }
        )

    effective_status = source_status
    if clause.clause_type is ClauseType.TERM or (
        clause.structural_profile is not None
        and clause.structural_profile.canonical_section is CanonicalDocumentSection.TERMINOLOGY
    ):
        effective_status = NormativeStatus.INFORMATIVE
        basis.append(
            {
                "kind": "clause_type",
                "status": NormativeStatus.INFORMATIVE.value,
                "value": clause.clause_type.value,
            }
        )
    elif clause.heading and _INFORMATIVE_LOCAL_HEADING.search(clause.heading):
        effective_status = NormativeStatus.INFORMATIVE
        basis.append(
            {
                "kind": "local_heading",
                "status": NormativeStatus.INFORMATIVE.value,
                "value": clause.heading,
            }
        )

    return {
        "source_status": source_status.value,
        "effective_status": effective_status.value,
        "fallback_status": _DEFAULT_STATUS.value,
        "basis": basis,
        "span_overrides": _informative_span_overrides(clause),
    }


def _known_context_routing(clause: Clause) -> ContextRouting | None:
    routing = clause.context_routing
    availability = clause.provenance.availability(_CONTEXT_ROUTING_PATH)
    if availability == "known":
        return routing
    if availability == "unknown":
        return None
    # Keep the same in-process/unattributed behaviour as canonical CBox projection:
    # a non-default value without provenance is visible, never silently discarded.
    if routing != ContextRouting():
        return routing
    return None


def _is_authoritative_scope_source(clause: Clause) -> bool:
    profile = clause.structural_profile
    return clause.clause_type is ClauseType.SCOPE or (
        profile is not None and profile.canonical_section is CanonicalDocumentSection.SCOPE
    )


def _scope_reach_is_authoritative(source: Clause, reach: ScopeReach) -> bool:
    if reach.kind in {ScopeReachKind.DOCUMENT, ScopeReachKind.PART}:
        return _is_authoritative_scope_source(source)
    return True


def _structural_scope_normative_qualifications(text: str) -> tuple[str, ...]:
    """Extract only explicit document-character statements from structural Scope text."""

    selected: list[str] = []
    for sentence in _SENTENCE_BOUNDARY.split(" ".join(text.split())):
        candidate = sentence.strip()
        if not candidate:
            continue
        if not (
            _INFORMATIVE_QUALIFICATION.search(candidate)
            or _EXPLICIT_NORMATIVE_SCOPE_QUALIFICATION.search(candidate)
        ):
            continue
        if candidate not in selected:
            selected.append(candidate)
    return tuple(selected)


def _scope_reaches_clause(
    document: EngineeringDocument,
    clause: Clause,
    reach: ScopeReach,
    *,
    by_id: dict[str, Clause],
) -> bool:
    target_document = reach.document_key or document.key.value
    if target_document != document.key.value:
        return False

    if reach.kind is ScopeReachKind.DOCUMENT:
        return True
    if reach.kind is ScopeReachKind.PART:
        return clause.reference.part == reach.part

    root_id = reach.clause_id or _resolve_reach_reference(document, reach.reference)
    if root_id is None:
        return False
    if reach.kind is ScopeReachKind.CLAUSE:
        return clause.id.value == root_id
    if reach.kind is ScopeReachKind.SUBTREE:
        return _is_descendant_or_same(clause.id.value, root_id, by_id=by_id)
    return False


def _resolve_reach_reference(document: EngineeringDocument, value: str | None) -> str | None:
    if not value:
        return None
    key = reference_key(value)
    matches = [
        clause.id.value
        for clause in document.clauses
        if key
        in {
            reference_key(clause.reference.clause),
            reference_key(clause.reference.as_text()),
        }
    ]
    return matches[0] if len(matches) == 1 else None


def _is_descendant_or_same(
    clause_id: str,
    root_id: str,
    *,
    by_id: dict[str, Clause],
) -> bool:
    current_id: str | None = clause_id
    seen: set[str] = set()
    while current_id is not None and current_id not in seen:
        if current_id == root_id:
            return True
        seen.add(current_id)
        current = by_id.get(current_id)
        if current is None or current.parent_id is None:
            return False
        current_id = current.parent_id.value
    return False


def _explicit_clause_status(
    clause: Clause,
    basis: list[dict[str, Any]],
) -> NormativeStatus | None:
    if clause.normative_status is not NormativeStatus.UNSPECIFIED:
        basis.append(
            {
                "kind": "clause_normative_status",
                "status": clause.normative_status.value,
                "value": clause.normative_status.value,
            }
        )
        return clause.normative_status

    profile = clause.structural_profile
    if profile is None or profile.annex_status is None:
        return None
    status = {
        AnnexStatus.NORMATIVE: NormativeStatus.NORMATIVE,
        AnnexStatus.INFORMATIVE: NormativeStatus.INFORMATIVE,
        AnnexStatus.UNSPECIFIED: NormativeStatus.UNSPECIFIED,
    }[profile.annex_status]
    if status is NormativeStatus.UNSPECIFIED:
        return None
    basis.append(
        {
            "kind": "annex_status",
            "status": status.value,
            "value": profile.annex_status.value,
        }
    )
    return status


def _scope_status(
    scopes: tuple[dict[str, Any], ...],
    basis: list[dict[str, Any]],
) -> NormativeStatus | None:
    signals: list[tuple[NormativeStatus, dict[str, Any]]] = []
    for scope in scopes:
        for qualification in scope.get("qualifications", ()):  # type: ignore[arg-type]
            text = str(qualification)
            status = _qualification_status(text)
            if status is None:
                continue
            signals.append(
                (
                    status,
                    {
                        "kind": "governing_scope_qualification",
                        "status": status.value,
                        "source_clause_id": scope.get("source_clause_id"),
                        "source_reference": scope.get("source_reference"),
                        "value": text,
                    },
                )
            )
    if not signals:
        return None
    basis.extend(item for _, item in signals)
    statuses = {status for status, _ in signals}
    if len(statuses) > 1:
        return NormativeStatus.MIXED
    return signals[0][0]


def _qualification_status(value: str) -> NormativeStatus | None:
    if _INFORMATIVE_QUALIFICATION.search(value):
        return NormativeStatus.INFORMATIVE
    if _NORMATIVE_QUALIFICATION.search(value):
        return NormativeStatus.NORMATIVE
    return None


def _informative_span_overrides(clause: Clause) -> list[dict[str, Any]]:
    profile = clause.structural_profile
    if profile is None:
        return []
    overrides = []
    for section in profile.semantic_sections:
        if section.role not in _INFORMATIVE_SECTION_ROLES:
            continue
        overrides.append(
            {
                "status": NormativeStatus.INFORMATIVE.value,
                "start_offset": section.start_offset,
                "end_offset": section.end_offset,
                "label": section.label,
                "role": section.role.value if section.role is not None else None,
            }
        )
    return overrides
