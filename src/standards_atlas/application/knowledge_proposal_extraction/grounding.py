"""Deterministic grounding of proposal evidence into canonical clause text."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from standards_atlas.domain.model import (
    Clause,
    EvidenceAnchor,
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


def ground_evidence_quote(clause: Clause, quote: str) -> EvidenceGroundingResult:
    """Resolve an exact evidence quote to one unique span in ``Clause.plain_text``.

    No whitespace, case or punctuation normalization is permitted. A quote that is
    absent or occurs more than once is intentionally left unresolved so automatic
    qualification cannot silently widen the evidence scope.
    """

    if not quote:
        return EvidenceGroundingResult(
            anchor=None,
            violation_kind=KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING,
            reason="evidence quote is empty",
        )
    text = clause.plain_text
    offsets = _matching_offsets(text, quote)
    if not offsets:
        return EvidenceGroundingResult(
            anchor=None,
            violation_kind=KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING,
            reason="evidence quote does not occur exactly in canonical clause text",
        )
    if len(offsets) > 1:
        return EvidenceGroundingResult(
            anchor=None,
            violation_kind=KnowledgeProposalViolationKind.AMBIGUOUS_GROUNDING,
            reason=f"evidence quote occurs {len(offsets)} times in canonical clause text",
        )

    start = offsets[0]
    end = start + len(quote)
    digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()
    anchor_digest = hashlib.sha256(
        f"{clause.id.value}|{start}|{end}|{digest}".encode()
    ).hexdigest()[:20]
    return EvidenceGroundingResult(
        anchor=EvidenceAnchor(
            id=f"evidence:{clause.id.value}:{anchor_digest}",
            clause_id=clause.id,
            start_offset=start,
            end_offset=end,
            content_hash=digest,
        )
    )


def _matching_offsets(text: str, quote: str) -> tuple[int, ...]:
    offsets: list[int] = []
    start = 0
    while True:
        offset = text.find(quote, start)
        if offset < 0:
            return tuple(offsets)
        offsets.append(offset)
        start = offset + 1
