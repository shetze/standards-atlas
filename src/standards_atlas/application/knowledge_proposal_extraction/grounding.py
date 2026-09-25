"""Deterministic grounding of proposal evidence into canonical clause surfaces."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    EvidenceAnchor,
    EvidenceSourceKind,
    KnowledgeProposalViolationKind,
)


@dataclass(frozen=True)
class EvidenceGroundingResult:
    """Exact-match grounding result for one model-supplied evidence quote."""

    anchor: EvidenceAnchor | None
    violation_kind: KnowledgeProposalViolationKind | None = None
    reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.anchor is not None


def ground_evidence_quote(
    clause: Clause,
    quote: str,
    *,
    source_kind: EvidenceSourceKind = EvidenceSourceKind.BODY,
    source_clause_id: ClauseId | None = None,
    semantic_context: Mapping[str, object] | None = None,
) -> EvidenceGroundingResult:
    """Resolve an exact evidence quote to one canonical clause surface.

    Entity evidence may resolve against the current clause or against a source surface
    explicitly transported by the canonical assertion CBox. Body evidence from another
    clause is accepted only when that clause is present in ``associative_context``; heading
    evidence may additionally resolve from ``ancestor_headings``. No whitespace, case or
    punctuation normalization is permitted. Ambiguous or unavailable surfaces remain
    unresolved so qualification cannot silently widen provenance.
    """

    if not quote:
        return EvidenceGroundingResult(
            anchor=None,
            violation_kind=KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING,
            reason="evidence quote is empty",
        )

    resolved_source_clause_id = source_clause_id or clause.id
    source = _evidence_source_text(
        clause,
        source_kind=source_kind,
        source_clause_id=resolved_source_clause_id,
        semantic_context=semantic_context,
    )
    if source is None:
        return EvidenceGroundingResult(
            anchor=None,
            violation_kind=KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING,
            reason=_missing_source_reason(
                clause,
                source_kind=source_kind,
                source_clause_id=resolved_source_clause_id,
            ),
        )

    offsets = _matching_offsets(source, quote)
    surface_name = (
        "canonical clause body"
        if source_kind is EvidenceSourceKind.BODY
        else ("canonical clause heading")
    )
    if not offsets:
        return EvidenceGroundingResult(
            anchor=None,
            violation_kind=KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING,
            reason=f"evidence quote does not occur exactly in {surface_name}",
        )
    if len(offsets) > 1:
        return EvidenceGroundingResult(
            anchor=None,
            violation_kind=KnowledgeProposalViolationKind.AMBIGUOUS_GROUNDING,
            reason=f"evidence quote occurs {len(offsets)} times in {surface_name}",
        )

    start = offsets[0]
    end = start + len(quote)
    digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()
    anchor_digest = hashlib.sha256(
        (f"{resolved_source_clause_id.value}|{source_kind.value}|{start}|{end}|{digest}").encode()
    ).hexdigest()[:20]
    return EvidenceGroundingResult(
        anchor=EvidenceAnchor(
            id=f"evidence:{resolved_source_clause_id.value}:{source_kind.value}:{anchor_digest}",
            source_clause_id=resolved_source_clause_id,
            source_kind=source_kind,
            start_offset=start,
            end_offset=end,
            content_hash=digest,
        )
    )


def evidence_source_text(
    anchor: EvidenceAnchor,
    clause: Clause,
    *,
    semantic_context: Mapping[str, object] | None = None,
) -> str | None:
    """Return the canonical source surface addressed by ``anchor`` when available locally."""

    return _evidence_source_text(
        clause,
        source_kind=anchor.source_kind,
        source_clause_id=anchor.source_clause_id,
        semantic_context=semantic_context,
    )


def _evidence_source_text(
    clause: Clause,
    *,
    source_kind: EvidenceSourceKind,
    source_clause_id: ClauseId,
    semantic_context: Mapping[str, object] | None,
) -> str | None:
    if source_kind is EvidenceSourceKind.BODY and source_clause_id == clause.id:
        return clause.plain_text
    if source_kind is EvidenceSourceKind.HEADING and source_clause_id == clause.id:
        return clause.heading

    context = semantic_context or {}
    if source_kind is EvidenceSourceKind.HEADING:
        heading = _context_surface_text(
            context.get("ancestor_headings"),
            source_clause_id=source_clause_id,
            field="heading",
        )
        if heading is not None:
            return heading

    return _context_surface_text(
        context.get("associative_context"),
        source_clause_id=source_clause_id,
        field="text" if source_kind is EvidenceSourceKind.BODY else "heading",
    )


def _context_surface_text(
    values: object,
    *,
    source_clause_id: ClauseId,
    field: str,
) -> str | None:
    if not isinstance(values, list):
        return None
    for item in values:
        if not isinstance(item, Mapping):
            continue
        if item.get("clause_id") != source_clause_id.value:
            continue
        value = item.get(field)
        return value if isinstance(value, str) else None
    return None


def _missing_source_reason(
    clause: Clause,
    *,
    source_kind: EvidenceSourceKind,
    source_clause_id: ClauseId,
) -> str:
    if source_kind is EvidenceSourceKind.BODY and source_clause_id != clause.id:
        return "body evidence source is not available in associative canonical context"
    if source_kind is EvidenceSourceKind.HEADING:
        return "heading evidence source is not available in canonical clause context"
    return "evidence source is not available in canonical clause context"


def _matching_offsets(text: str, quote: str) -> tuple[int, ...]:
    offsets: list[int] = []
    start = 0
    while True:
        offset = text.find(quote, start)
        if offset < 0:
            return tuple(offsets)
        offsets.append(offset)
        start = offset + 1
