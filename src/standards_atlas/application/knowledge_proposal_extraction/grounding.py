"""Deterministic grounding of proposal evidence into canonical clause surfaces."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.context.input_binding import (
    BoundContextInputSurface,
    ContextSourcePackage,
)
from standards_atlas.application.knowledge_proposal_extraction.projection import (
    is_non_evidence_projection_marker,
)
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

    return EvidenceGroundingResult(
        anchor=_evidence_anchor(
            source_clause_id=resolved_source_clause_id,
            source_kind=source_kind,
            quote=quote,
            start=offsets[0],
        )
    )


def ground_entity_evidence_quote(
    clause: Clause,
    quote: str,
    *,
    source_kind: EvidenceSourceKind = EvidenceSourceKind.BODY,
    source_clause_id: ClauseId | None = None,
    semantic_context: Mapping[str, object] | None = None,
) -> EvidenceGroundingResult:
    """Ground entity evidence, recovering an incorrectly declared source surface.

    The LLM still declares an intended source clause and surface. That declaration is tried
    first. If it cannot resolve the exact quote, the quote is searched deterministically over
    every entity-evidence surface explicitly allowed by the canonical CBox: local body and
    heading, ancestor headings, and body/heading surfaces in ``associative_context``. Recovery
    succeeds only when the quote occurs exactly once across all allowed surfaces. Assertions do
    not use this fallback and therefore remain strictly local-body grounded.
    """

    declared = ground_evidence_quote(
        clause,
        quote,
        source_kind=source_kind,
        source_clause_id=source_clause_id,
        semantic_context=semantic_context,
    )
    if (
        declared.resolved
        or declared.violation_kind is KnowledgeProposalViolationKind.AMBIGUOUS_GROUNDING
    ):
        return declared
    if not quote:
        return declared

    matches: list[tuple[ClauseId, EvidenceSourceKind, int]] = []
    for candidate_clause_id, candidate_kind, source in _entity_evidence_surfaces(
        clause,
        semantic_context=semantic_context,
    ):
        for offset in _matching_offsets(source, quote):
            matches.append((candidate_clause_id, candidate_kind, offset))

    if not matches:
        return declared
    if len(matches) > 1:
        return EvidenceGroundingResult(
            anchor=None,
            violation_kind=KnowledgeProposalViolationKind.AMBIGUOUS_GROUNDING,
            reason=(
                f"evidence quote occurs {len(matches)} times across canonical entity evidence "
                "surfaces"
            ),
        )

    resolved_clause_id, resolved_kind, start = matches[0]
    return EvidenceGroundingResult(
        anchor=_evidence_anchor(
            source_clause_id=resolved_clause_id,
            source_kind=resolved_kind,
            quote=quote,
            start=start,
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


def _entity_evidence_surfaces(
    clause: Clause,
    *,
    semantic_context: Mapping[str, object] | None,
) -> tuple[tuple[ClauseId, EvidenceSourceKind, str], ...]:
    surfaces: list[tuple[ClauseId, EvidenceSourceKind, str]] = [
        (clause.id, EvidenceSourceKind.BODY, clause.plain_text),
    ]
    if clause.heading:
        surfaces.append((clause.id, EvidenceSourceKind.HEADING, clause.heading))

    context = semantic_context or {}
    ancestor_headings = context.get("ancestor_headings")
    if isinstance(ancestor_headings, list):
        for item in ancestor_headings:
            if not isinstance(item, Mapping):
                continue
            clause_id = item.get("clause_id")
            heading = item.get("heading")
            if isinstance(clause_id, str) and isinstance(heading, str) and heading:
                surfaces.append((ClauseId(value=clause_id), EvidenceSourceKind.HEADING, heading))

    associative_context = context.get("associative_context")
    if isinstance(associative_context, list):
        for item in associative_context:
            if not isinstance(item, Mapping):
                continue
            clause_id = item.get("clause_id")
            if not isinstance(clause_id, str):
                continue
            body = item.get("text")
            heading = item.get("heading")
            if isinstance(body, str) and body:
                surfaces.append((ClauseId(value=clause_id), EvidenceSourceKind.BODY, body))
            if isinstance(heading, str) and heading:
                surfaces.append((ClauseId(value=clause_id), EvidenceSourceKind.HEADING, heading))

    unique: list[tuple[ClauseId, EvidenceSourceKind, str]] = []
    seen: set[tuple[str, EvidenceSourceKind, str]] = set()
    for source_clause_id, source_kind, source in surfaces:
        key = (source_clause_id.value, source_kind, source)
        if key in seen:
            continue
        seen.add(key)
        unique.append((source_clause_id, source_kind, source))
    return tuple(unique)


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


def _evidence_anchor(
    *,
    source_clause_id: ClauseId,
    source_kind: EvidenceSourceKind,
    quote: str,
    start: int,
) -> EvidenceAnchor:
    end = start + len(quote)
    digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()
    anchor_digest = hashlib.sha256(
        (f"{source_clause_id.value}|{source_kind.value}|{start}|{end}|{digest}").encode()
    ).hexdigest()[:20]
    return EvidenceAnchor(
        id=f"evidence:{source_clause_id.value}:{source_kind.value}:{anchor_digest}",
        source_clause_id=source_clause_id,
        source_kind=source_kind,
        start_offset=start,
        end_offset=end,
        content_hash=digest,
    )


class EvidenceGroundingOwnerKind(StrEnum):
    """Proposal object kind using the common evidence grounding contract."""

    ENTITY = "entity"
    ASSERTION = "assertion"


class EvidenceContribution(StrEnum):
    """Proposed role of one evidence use; this is not semantic confirmation."""

    DIRECT_STATEMENT = "direct_statement"
    SUBJECT_FRAME = "subject_frame"
    CONDITION_OR_EXCEPTION = "condition_or_exception"


class EvidenceGroundingFailureCode(StrEnum):
    """Technical multi-span grounding failure without semantic interpretation."""

    SOURCE_NOT_DELIVERED = "source_not_delivered"
    UNSUPPORTED_SOURCE_SURFACE = "unsupported_source_surface"
    EMPTY_QUOTE = "empty_quote"
    QUOTE_NOT_FOUND = "quote_not_found"
    AMBIGUOUS_QUOTE = "ambiguous_quote"
    SELECTOR_MISMATCH = "selector_mismatch"
    OFFSETS_OUTSIDE_DELIVERED_EXCERPT = "offsets_outside_delivered_excerpt"
    OCCURRENCE_OUT_OF_RANGE = "occurrence_out_of_range"
    UNQUOTEABLE_PROJECTION_MARKER = "unquoteable_projection_marker"


class UniqueQuoteSelector(BaseModel):
    """Require that the exact quote occurs once in the declared delivered excerpt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["unique"] = "unique"


class CanonicalOffsetSelector(BaseModel):
    """Select a quote by absolute canonical character offsets [start, end)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["canonical_offsets"] = "canonical_offsets"
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)

    @model_validator(mode="after")
    def offsets_form_non_empty_range(self) -> CanonicalOffsetSelector:
        if self.end_offset <= self.start_offset:
            raise ValueError("canonical evidence offsets must form a non-empty range")
        return self


class QuoteOccurrenceSelector(BaseModel):
    """Select a zero-based exact occurrence inside the declared delivered excerpt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["occurrence"] = "occurrence"
    occurrence_index: int = Field(ge=0)


type EvidenceSelector = Annotated[
    UniqueQuoteSelector | CanonicalOffsetSelector | QuoteOccurrenceSelector,
    Field(discriminator="kind"),
]


class EvidenceUse(BaseModel):
    """One declared use of one exact span from the bound input package."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ref: str = Field(min_length=1)
    exact_quote: str
    selector: EvidenceSelector = UniqueQuoteSelector()
    contribution: EvidenceContribution = EvidenceContribution.DIRECT_STATEMENT


class EvidenceGroundingRequest(BaseModel):
    """Common multi-span request used identically for entity and assertion evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_kind: EvidenceGroundingOwnerKind
    owner_id: str = Field(min_length=1)
    evidence: tuple[EvidenceUse, ...] = ()


class GroundedEvidenceUse(BaseModel):
    """Technically bound use; contribution remains proposed/unconfirmed semantics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    use_index: int = Field(ge=0)
    anchor_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    contribution: EvidenceContribution
    assessment_status: Literal["technically_bound"] = "technically_bound"
    semantic_status: Literal["unassessed"] = "unassessed"


class EvidenceGroundingFailure(BaseModel):
    """One failed declared span; reasons intentionally do not echo protected source text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    use_index: int = Field(ge=0)
    source_ref: str = Field(min_length=1)
    code: EvidenceGroundingFailureCode
    reason: str = Field(min_length=1)


class MultiSpanEvidenceGroundingResult(BaseModel):
    """All-or-complete grounding status while retaining partial diagnostics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_kind: EvidenceGroundingOwnerKind
    owner_id: str = Field(min_length=1)
    anchors: tuple[EvidenceAnchor, ...] = ()
    grounded_uses: tuple[GroundedEvidenceUse, ...] = ()
    failures: tuple[EvidenceGroundingFailure, ...] = ()
    complete: bool

    @model_validator(mode="after")
    def completeness_matches_failures(self) -> MultiSpanEvidenceGroundingResult:
        if self.complete != (not self.failures):
            raise ValueError("multi-span grounding completeness must reflect all declared spans")
        return self


def ground_evidence_request(
    package: ContextSourcePackage,
    request: EvidenceGroundingRequest,
) -> MultiSpanEvidenceGroundingResult:
    """Ground all declared spans against only the exact surfaces in ``package.input_surfaces``.

    No fallback search across other package surfaces or the wider document is performed.  A valid
    span may remain available for diagnostics when another span fails, but ``complete`` is false so
    callers cannot silently treat the surviving subset as fully grounded evidence.
    """

    surfaces = {surface.package_source_ref: surface for surface in package.input_surfaces}
    anchors_by_id: dict[str, EvidenceAnchor] = {}
    grounded: list[GroundedEvidenceUse] = []
    failures: list[EvidenceGroundingFailure] = []

    for index, evidence_use in enumerate(request.evidence):
        surface = surfaces.get(evidence_use.source_ref)
        if surface is None:
            failures.append(
                EvidenceGroundingFailure(
                    use_index=index,
                    source_ref=evidence_use.source_ref,
                    code=EvidenceGroundingFailureCode.SOURCE_NOT_DELIVERED,
                    reason="declared evidence source is not part of the bound actual input",
                )
            )
            continue
        grounded_anchor, failure = _ground_bound_evidence_use(surface, evidence_use, index=index)
        if failure is not None:
            failures.append(failure)
            continue
        assert grounded_anchor is not None
        anchors_by_id.setdefault(grounded_anchor.id, grounded_anchor)
        grounded.append(
            GroundedEvidenceUse(
                use_index=index,
                anchor_id=grounded_anchor.id,
                source_ref=evidence_use.source_ref,
                contribution=evidence_use.contribution,
            )
        )

    return MultiSpanEvidenceGroundingResult(
        owner_kind=request.owner_kind,
        owner_id=request.owner_id,
        anchors=tuple(anchors_by_id.values()),
        grounded_uses=tuple(grounded),
        failures=tuple(failures),
        complete=not failures,
    )


def _ground_bound_evidence_use(
    surface: BoundContextInputSurface,
    evidence_use: EvidenceUse,
    *,
    index: int,
) -> tuple[EvidenceAnchor | None, EvidenceGroundingFailure | None]:
    if surface.source_ref.source_kind not in {EvidenceSourceKind.BODY, EvidenceSourceKind.HEADING}:
        return None, _multi_span_failure(
            index,
            evidence_use,
            EvidenceGroundingFailureCode.UNSUPPORTED_SOURCE_SURFACE,
            "current EvidenceAnchor contract cannot address the declared media surface",
        )
    if evidence_use.exact_quote == "":
        return None, _multi_span_failure(
            index,
            evidence_use,
            EvidenceGroundingFailureCode.EMPTY_QUOTE,
            "evidence quote is empty",
        )
    if is_non_evidence_projection_marker(evidence_use.exact_quote):
        return None, _multi_span_failure(
            index,
            evidence_use,
            EvidenceGroundingFailureCode.UNQUOTEABLE_PROJECTION_MARKER,
            "extractor table-omission markers are display metadata, not source evidence",
        )

    selector = evidence_use.selector
    if isinstance(selector, CanonicalOffsetSelector):
        if selector.start_offset < surface.start_offset or selector.end_offset > surface.end_offset:
            return None, _multi_span_failure(
                index,
                evidence_use,
                EvidenceGroundingFailureCode.OFFSETS_OUTSIDE_DELIVERED_EXCERPT,
                "canonical selector lies outside the declared delivered excerpt",
            )
        local_start = selector.start_offset - surface.start_offset
        local_end = selector.end_offset - surface.start_offset
        if surface.text[local_start:local_end] != evidence_use.exact_quote:
            return None, _multi_span_failure(
                index,
                evidence_use,
                EvidenceGroundingFailureCode.SELECTOR_MISMATCH,
                "canonical selector and exact quote do not identify the same delivered text",
            )
        canonical_start = selector.start_offset
    else:
        matches = _matching_offsets(surface.text, evidence_use.exact_quote)
        if not matches:
            return None, _multi_span_failure(
                index,
                evidence_use,
                EvidenceGroundingFailureCode.QUOTE_NOT_FOUND,
                "exact quote does not occur in the declared delivered excerpt",
            )
        if isinstance(selector, UniqueQuoteSelector):
            if len(matches) != 1:
                return None, _multi_span_failure(
                    index,
                    evidence_use,
                    EvidenceGroundingFailureCode.AMBIGUOUS_QUOTE,
                    "exact quote occurs more than once in the declared delivered excerpt",
                )
            local_start = matches[0]
        else:
            if selector.occurrence_index >= len(matches):
                return None, _multi_span_failure(
                    index,
                    evidence_use,
                    EvidenceGroundingFailureCode.OCCURRENCE_OUT_OF_RANGE,
                    "requested quote occurrence is outside the delivered excerpt match set",
                )
            local_start = matches[selector.occurrence_index]
        canonical_start = surface.start_offset + local_start

    assert surface.source_ref.source_kind is not None
    return (
        _evidence_anchor(
            source_clause_id=ClauseId(value=surface.identity.clause_id),
            source_kind=surface.source_ref.source_kind,
            quote=evidence_use.exact_quote,
            start=canonical_start,
        ),
        None,
    )


def _multi_span_failure(
    index: int,
    evidence_use: EvidenceUse,
    code: EvidenceGroundingFailureCode,
    reason: str,
) -> EvidenceGroundingFailure:
    return EvidenceGroundingFailure(
        use_index=index,
        source_ref=evidence_use.source_ref,
        code=code,
        reason=reason,
    )
