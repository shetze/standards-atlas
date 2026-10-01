"""Versioned deterministic selection and character budgeting for AP02 context candidates."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.context.source_surfaces import SourceSurfaceAvailability
from standards_atlas.application.context.structured_candidates import (
    ContextCandidate,
    ContextCandidateReason,
    ContextDiagnosticCode,
    StructuredContextCandidates,
)
from standards_atlas.domain.model import EvidenceSourceKind

STRUCTURED_CONTEXT_SELECTION_CONTRACT = "structured-context-selection-v1"
DEFAULT_CONTEXT_SELECTION_PROFILE_ID = "assertion-context-selection-v1"


class ContextSelectionCompleteness(StrEnum):
    """Technical selection state, explicitly not an adoption/release decision."""

    COMPLETE = "complete"
    BOUNDED = "bounded"
    INCOMPLETE = "incomplete"
    INPUT_BUDGET_EXCEEDED = "input_budget_exceeded"


class ContextSelectionReason(StrEnum):
    TARGET_CORE = "target_core"
    EXPLICIT_REFERENCE = "explicit_reference"
    ANCESTOR_CONTEXT = "ancestor_context"
    SEQUENTIAL_CONTEXT = "sequential_context"


class ContextOmissionReason(StrEnum):
    SOURCE_UNAVAILABLE = "source_unavailable"
    NON_TEXTUAL = "non_textual"
    OUTSIDE_SEQUENCE_WINDOW = "outside_sequence_window"
    BUDGET_EXCEEDED = "budget_exceeded"
    INPUT_BUDGET_EXCEEDED = "input_budget_exceeded"


class ContextReachHint(StrEnum):
    TARGET_SOURCE = "target_source"
    STRUCTURAL_ANCESTOR = "structural_ancestor"
    SAME_PARENT_SEQUENCE = "same_parent_sequence"
    EXPLICIT_REFERENCE = "explicit_reference"
    REVERSE_REFERENCE_TO_TARGET_OR_SEQUENCE = "reverse_reference_to_target_or_sequence"
    EXTERNAL_REFERENCE = "external_reference"


class ContextSelectionProfile(BaseModel):
    """Versioned deterministic policy for a bounded source-context projection.

    The budget is a character budget, never reported as tokens.  Fixed/per-surface overhead reserves
    space for the later renderer and administrative fields; S05 binds the actual rendered input.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: Literal["assertion-context-selection-v1"] = DEFAULT_CONTEXT_SELECTION_PROFILE_ID
    character_budget: int = Field(default=12_000, ge=1)
    fixed_overhead_chars: int = Field(default=256, ge=0)
    per_surface_overhead_chars: int = Field(default=96, ge=0)
    max_sequence_distance: int = Field(default=4, ge=0)


class ContextSelectionEntry(BaseModel):
    """One selected source surface with reasons but without semantic confirmation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate: ContextCandidate
    selection_reason: ContextSelectionReason
    reach_hints: tuple[ContextReachHint, ...] = Field(min_length=1)
    semantic_reach_confirmed: Literal[False] = False
    estimated_character_cost: int = Field(ge=0)


class ContextOmittedEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate: ContextCandidate
    reason: ContextOmissionReason
    detail: str = Field(min_length=1)
    estimated_character_cost: int = Field(ge=0)


class ContextSelectionGap(BaseModel):
    """Selection-relevant known gap without inventing missing content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    source_clause_id: str | None = None
    source_document_key: str | None = None


class StructuredContextSelection(BaseModel):
    """Reproducible bounded selection over a fixed candidate inventory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: Literal["structured-context-selection-v1"] = STRUCTURED_CONTEXT_SELECTION_CONTRACT
    profile: ContextSelectionProfile
    candidate_contract_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    document_revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_clause_id: str = Field(min_length=1)
    target_reference: str = Field(min_length=1)
    selected: tuple[ContextSelectionEntry, ...] = ()
    omitted: tuple[ContextOmittedEntry, ...] = ()
    gaps: tuple[ContextSelectionGap, ...] = ()
    completeness: ContextSelectionCompleteness
    budget_used_chars: int = Field(ge=0)
    budget_remaining_chars: int = Field(ge=0)


def select_structured_context(
    inventory: StructuredContextCandidates,
    *,
    profile: ContextSelectionProfile | None = None,
) -> StructuredContextSelection:
    """Apply deterministic reach-neutral prioritization and character budgeting.

    Foreign candidates never become semantically confirmed here.  First-leaf position, wording and
    proximity are not semantic reach rules.  Later reverse references are prioritized alongside
    direct references; ordinary sequential candidates are ordered symmetrically by distance with a
    forward candidate before an equally distant backward candidate.
    """

    policy = profile or ContextSelectionProfile()
    fixed = policy.fixed_overhead_chars
    available_budget = max(policy.character_budget - fixed, 0)

    target_candidates = tuple(
        candidate
        for candidate in inventory.candidates
        if candidate.reach_status == "target"
        and candidate.resolution.availability is SourceSurfaceAvailability.AVAILABLE
    )
    target_unavailable = tuple(
        candidate
        for candidate in inventory.candidates
        if candidate.reach_status == "target"
        and candidate.resolution.availability is not SourceSurfaceAvailability.AVAILABLE
    )
    target_candidates = tuple(sorted(target_candidates, key=_target_surface_key))
    target_cost = sum(_candidate_cost(item, policy) for item in target_candidates)

    if fixed > policy.character_budget or target_cost > available_budget:
        omitted = tuple(
            ContextOmittedEntry(
                candidate=item,
                reason=ContextOmissionReason.INPUT_BUDGET_EXCEEDED,
                detail="target source content does not fit the configured character budget",
                estimated_character_cost=_candidate_cost(item, policy),
            )
            for item in target_candidates
        )
        return StructuredContextSelection(
            profile=policy,
            candidate_contract_id=inventory.contract_id,
            document_key=inventory.document_key,
            document_revision=inventory.document_revision,
            target_clause_id=inventory.target_clause_id,
            target_reference=inventory.target_reference,
            selected=(),
            omitted=omitted,
            gaps=(
                ContextSelectionGap(
                    code=ContextSelectionCompleteness.INPUT_BUDGET_EXCEEDED.value,
                    detail="target source content was not truncated to satisfy the budget",
                    source_clause_id=inventory.target_clause_id,
                    source_document_key=inventory.document_key,
                ),
            ),
            completeness=ContextSelectionCompleteness.INPUT_BUDGET_EXCEEDED,
            budget_used_chars=fixed,
            budget_remaining_chars=max(policy.character_budget - fixed, 0),
        )

    selected: list[ContextSelectionEntry] = []
    omitted: list[ContextOmittedEntry] = []
    gaps = _diagnostic_gaps(inventory)
    used = fixed

    for candidate in target_unavailable:
        availability = candidate.resolution.availability
        omitted.append(
            ContextOmittedEntry(
                candidate=candidate,
                reason=ContextOmissionReason.SOURCE_UNAVAILABLE,
                detail=f"target source surface is {availability.value}",
                estimated_character_cost=_candidate_cost(candidate, policy),
            )
        )
        if availability in {
            SourceSurfaceAvailability.NOT_AUTHORIZED,
            SourceSurfaceAvailability.NOT_LOADED,
            SourceSurfaceAvailability.CONFLICTING,
        }:
            gaps.append(
                ContextSelectionGap(
                    code=availability.value,
                    detail="target source content could not be supplied",
                    source_clause_id=candidate.source_ref.clause_id,
                    source_document_key=candidate.source_ref.document_key,
                )
            )

    for candidate in target_candidates:
        cost = _candidate_cost(candidate, policy)
        selected.append(_selected_entry(candidate, ContextSelectionReason.TARGET_CORE, cost))
        used += cost

    non_target = [
        candidate for candidate in inventory.candidates if candidate.reach_status != "target"
    ]
    for candidate in sorted(non_target, key=_selection_key):
        cost = _candidate_cost(candidate, policy)
        availability = candidate.resolution.availability
        if availability is SourceSurfaceAvailability.NON_TEXTUAL:
            omitted.append(
                ContextOmittedEntry(
                    candidate=candidate,
                    reason=ContextOmissionReason.NON_TEXTUAL,
                    detail=(
                        "non-textual source handles are visible but not copied into text context"
                    ),
                    estimated_character_cost=cost,
                )
            )
            continue
        if availability is not SourceSurfaceAvailability.AVAILABLE:
            omitted.append(
                ContextOmittedEntry(
                    candidate=candidate,
                    reason=ContextOmissionReason.SOURCE_UNAVAILABLE,
                    detail=f"source surface is {availability.value}",
                    estimated_character_cost=cost,
                )
            )
            if availability in {
                SourceSurfaceAvailability.NOT_AUTHORIZED,
                SourceSurfaceAvailability.NOT_LOADED,
                SourceSurfaceAvailability.CONFLICTING,
            }:
                gaps.append(
                    ContextSelectionGap(
                        code=availability.value,
                        detail="reachable context source could not be supplied",
                        source_clause_id=candidate.source_ref.clause_id,
                        source_document_key=candidate.source_ref.document_key,
                    )
                )
            continue
        if _outside_sequence_window(candidate, policy.max_sequence_distance):
            omitted.append(
                ContextOmittedEntry(
                    candidate=candidate,
                    reason=ContextOmissionReason.OUTSIDE_SEQUENCE_WINDOW,
                    detail="sequential candidate lies outside the configured structural window",
                    estimated_character_cost=cost,
                )
            )
            continue
        if used + cost > policy.character_budget:
            omitted.append(
                ContextOmittedEntry(
                    candidate=candidate,
                    reason=ContextOmissionReason.BUDGET_EXCEEDED,
                    detail="complete addressed source surface does not fit the remaining budget",
                    estimated_character_cost=cost,
                )
            )
            gaps.append(
                ContextSelectionGap(
                    code=ContextOmissionReason.BUDGET_EXCEEDED.value,
                    detail="reachable context was omitted rather than silently truncated",
                    source_clause_id=candidate.source_ref.clause_id,
                    source_document_key=candidate.source_ref.document_key,
                )
            )
            continue
        reason = _selection_reason(candidate)
        selected.append(_selected_entry(candidate, reason, cost))
        used += cost

    completeness = _completeness(omitted, gaps)
    return StructuredContextSelection(
        profile=policy,
        candidate_contract_id=inventory.contract_id,
        document_key=inventory.document_key,
        document_revision=inventory.document_revision,
        target_clause_id=inventory.target_clause_id,
        target_reference=inventory.target_reference,
        selected=tuple(selected),
        omitted=tuple(omitted),
        gaps=tuple(_dedupe_gaps(gaps)),
        completeness=completeness,
        budget_used_chars=used,
        budget_remaining_chars=max(policy.character_budget - used, 0),
    )


def _candidate_cost(candidate: ContextCandidate, profile: ContextSelectionProfile) -> int:
    text = candidate.resolution.text or ""
    return len(text) + profile.per_surface_overhead_chars


def _target_surface_key(candidate: ContextCandidate) -> tuple[int, str]:
    # Own source-backed heading and body are both core.  Heading first keeps the subject frame
    # visible in diagnostics but does not change the all-or-nothing target budget gate.
    order = 0 if candidate.source_ref.source_kind is EvidenceSourceKind.HEADING else 1
    return order, candidate.candidate_id


def _selection_key(candidate: ContextCandidate) -> tuple[int, int, int, int, str]:
    reasons = set(candidate.reasons)
    if ContextCandidateReason.REVERSE_INTERNAL_REFERENCE in reasons:
        bucket = 0
    elif ContextCandidateReason.DIRECT_INTERNAL_REFERENCE in reasons:
        bucket = 1
    elif ContextCandidateReason.EXPLICIT_EXTERNAL_REFERENCE in reasons:
        bucket = 2
    elif {
        ContextCandidateReason.ANCESTOR_BODY,
        ContextCandidateReason.ANCESTOR_HEADING,
    } & reasons:
        bucket = 3
    else:
        bucket = 4

    distances = [path.distance for path in candidate.paths if path.distance is not None]
    distance = min(distances) if distances else 0
    directions = {path.direction for path in candidate.paths}
    direction_order = 0 if "forward" in directions else 1 if "backward" in directions else 2

    if ContextCandidateReason.ANCESTOR_HEADING in reasons:
        surface_order = 0
    elif candidate.source_ref.source_kind is EvidenceSourceKind.BODY:
        surface_order = 0
    else:
        surface_order = 1
    return bucket, distance, direction_order, surface_order, candidate.candidate_id


def _outside_sequence_window(candidate: ContextCandidate, max_distance: int) -> bool:
    sequence_paths = [
        path
        for path in candidate.paths
        if path.kind.value == "sequence" and path.distance is not None
    ]
    if not sequence_paths:
        return False
    if {
        ContextCandidateReason.REVERSE_INTERNAL_REFERENCE,
        ContextCandidateReason.DIRECT_INTERNAL_REFERENCE,
    } & set(candidate.reasons):
        return False
    return min(path.distance or 0 for path in sequence_paths) > max_distance


def _selection_reason(candidate: ContextCandidate) -> ContextSelectionReason:
    reasons = set(candidate.reasons)
    if {
        ContextCandidateReason.REVERSE_INTERNAL_REFERENCE,
        ContextCandidateReason.DIRECT_INTERNAL_REFERENCE,
        ContextCandidateReason.EXPLICIT_EXTERNAL_REFERENCE,
    } & reasons:
        return ContextSelectionReason.EXPLICIT_REFERENCE
    if {
        ContextCandidateReason.ANCESTOR_BODY,
        ContextCandidateReason.ANCESTOR_HEADING,
    } & reasons:
        return ContextSelectionReason.ANCESTOR_CONTEXT
    return ContextSelectionReason.SEQUENTIAL_CONTEXT


def _selected_entry(
    candidate: ContextCandidate,
    reason: ContextSelectionReason,
    cost: int,
) -> ContextSelectionEntry:
    return ContextSelectionEntry(
        candidate=candidate,
        selection_reason=reason,
        reach_hints=_reach_hints(candidate),
        estimated_character_cost=cost,
    )


def _reach_hints(candidate: ContextCandidate) -> tuple[ContextReachHint, ...]:
    if candidate.reach_status == "target":
        return (ContextReachHint.TARGET_SOURCE,)
    reasons = set(candidate.reasons)
    hints: list[ContextReachHint] = []
    if {
        ContextCandidateReason.ANCESTOR_BODY,
        ContextCandidateReason.ANCESTOR_HEADING,
    } & reasons:
        hints.append(ContextReachHint.STRUCTURAL_ANCESTOR)
    if {
        ContextCandidateReason.SEQUENCE_PREVIOUS,
        ContextCandidateReason.SEQUENCE_NEXT,
        ContextCandidateReason.FIRST_LEAF_CANDIDATE,
    } & reasons:
        hints.append(ContextReachHint.SAME_PARENT_SEQUENCE)
    if ContextCandidateReason.DIRECT_INTERNAL_REFERENCE in reasons:
        hints.append(ContextReachHint.EXPLICIT_REFERENCE)
    if ContextCandidateReason.REVERSE_INTERNAL_REFERENCE in reasons:
        hints.append(ContextReachHint.REVERSE_REFERENCE_TO_TARGET_OR_SEQUENCE)
    if ContextCandidateReason.EXPLICIT_EXTERNAL_REFERENCE in reasons:
        hints.append(ContextReachHint.EXTERNAL_REFERENCE)
    return tuple(hints) or (ContextReachHint.SAME_PARENT_SEQUENCE,)


def _diagnostic_gaps(inventory: StructuredContextCandidates) -> list[ContextSelectionGap]:
    gaps: list[ContextSelectionGap] = []
    for diagnostic in inventory.diagnostics:
        if diagnostic.code is ContextDiagnosticCode.SOURCE_UNAVAILABLE:
            # Expected absence of a body on a heading-only structural node is already visible on
            # the candidate.  It is not by itself evidence that required context is missing.
            continue
        gaps.append(
            ContextSelectionGap(
                code=diagnostic.code.value,
                detail=diagnostic.message,
                source_clause_id=diagnostic.source_clause_id,
                source_document_key=diagnostic.target_document_key,
            )
        )
    return gaps


def _completeness(
    omitted: list[ContextOmittedEntry],
    gaps: list[ContextSelectionGap],
) -> ContextSelectionCompleteness:
    if gaps or any(
        item.reason is ContextOmissionReason.BUDGET_EXCEEDED
        or (
            item.reason is ContextOmissionReason.SOURCE_UNAVAILABLE
            and item.candidate.resolution.availability
            not in {SourceSurfaceAvailability.MISSING, SourceSurfaceAvailability.NON_TEXTUAL}
        )
        for item in omitted
    ):
        return ContextSelectionCompleteness.INCOMPLETE
    if omitted:
        return ContextSelectionCompleteness.BOUNDED
    return ContextSelectionCompleteness.COMPLETE


def _dedupe_gaps(values: list[ContextSelectionGap]) -> tuple[ContextSelectionGap, ...]:
    unique: dict[tuple[object, ...], ContextSelectionGap] = {}
    for value in values:
        key = (value.code, value.detail, value.source_clause_id, value.source_document_key)
        unique[key] = value
    return tuple(unique.values())
