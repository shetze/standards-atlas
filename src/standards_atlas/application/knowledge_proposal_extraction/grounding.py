"""Source-bound multi-span grounding into canonical evidence anchors."""

from __future__ import annotations

import hashlib
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
from standards_atlas.domain.model import ClauseId, EvidenceAnchor, EvidenceSourceKind


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
