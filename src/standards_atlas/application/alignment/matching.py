"""Candidate indexing and monotone initial alignment selection."""

from __future__ import annotations

from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Protocol

from standards_atlas.application.model.alignment import (
    AlignmentIssue,
    AlignmentOptions,
    AlignmentStatus,
    ClauseAlignment,
)
from standards_atlas.application.model.reference_candidates import (
    CandidateRemainderKind,
    ReferenceCandidate,
    ReferenceCandidateDocument,
    ReferenceMatchKind,
)
from standards_atlas.domain.model import Clause


class ExpectedClause(Protocol):
    """Structural view required by the initial matcher."""

    clause: Clause
    index: int


def candidate_index(
    document: ReferenceCandidateDocument,
) -> dict[str, list[ReferenceCandidate]]:
    """Index candidates by expected clause id in document order."""
    index: dict[str, list[ReferenceCandidate]] = {}
    for candidate in document.candidates:
        for clause_id in candidate.expected_clause_ids:
            index.setdefault(clause_id, []).append(candidate)
    for values in index.values():
        values.sort(key=lambda candidate: candidate.sequence_number)
    return index


def candidate_score(candidate: ReferenceCandidate, clause: Clause) -> float:
    """Calculate the deterministic selection score used by alignment."""
    title_score = 0.0
    if (
        candidate.remainder_kind is CandidateRemainderKind.TITLE
        and candidate.title_remainder
        and clause.heading
    ):
        title_score = SequenceMatcher(
            None,
            candidate.title_remainder.casefold(),
            clause.heading.casefold(),
        ).ratio()
    kind_bonus = {
        ReferenceMatchKind.EXACT: 0.05,
        ReferenceMatchKind.ANNEX: 0.04,
        ReferenceMatchKind.NORMALIZED: 0.02,
        ReferenceMatchKind.INLINE: 0.0,
    }[candidate.match_kind]
    return candidate.confidence + kind_bonus + (0.1 * title_score)


def select_monotone(
    expected: Sequence[ExpectedClause],
    indexed_candidates: dict[str, list[ReferenceCandidate]],
) -> tuple[
    dict[str, ReferenceCandidate],
    dict[str, tuple[str, ...]],
    list[AlignmentIssue],
]:
    """Select one candidate per clause while preserving expected order."""
    selected: dict[str, ReferenceCandidate] = {}
    alternatives: dict[str, tuple[str, ...]] = {}
    issues: list[AlignmentIssue] = []
    last_sequence = -1
    for entry in expected:
        clause_id = entry.clause.id.value
        all_candidates = indexed_candidates.get(clause_id, [])
        eligible = [
            candidate for candidate in all_candidates if candidate.sequence_number > last_sequence
        ]
        if not eligible:
            if all_candidates:
                issues.append(
                    AlignmentIssue(
                        code="OUT_OF_ORDER_REFERENCE",
                        severity="error",
                        clause_ids=(clause_id,),
                        item_ids=tuple(candidate.item_id for candidate in all_candidates),
                        message=(
                            f"All candidates for {entry.clause.reference.clause!r} "
                            "violate the expected clause order."
                        ),
                    )
                )
            continue
        chosen = max(
            eligible,
            key=lambda candidate: (
                candidate_score(candidate, entry.clause),
                -candidate.sequence_number,
            ),
        )
        selected[clause_id] = chosen
        last_sequence = chosen.sequence_number
        discarded = tuple(
            candidate.item_id for candidate in all_candidates if candidate.item_id != chosen.item_id
        )
        alternatives[clause_id] = discarded
        if discarded:
            issues.append(
                AlignmentIssue(
                    code="DUPLICATE_REFERENCE",
                    clause_ids=(clause_id,),
                    item_ids=(chosen.item_id, *discarded),
                    message=(
                        "Multiple candidates were found for "
                        f"{entry.clause.reference.clause!r}; one was selected."
                    ),
                )
            )
    return selected, alternatives, issues


def initial_alignments(
    expected: Sequence[ExpectedClause],
    selected: dict[str, ReferenceCandidate],
    alternatives: dict[str, tuple[str, ...]],
    issues: list[AlignmentIssue],
    options: AlignmentOptions,
) -> list[ClauseAlignment]:
    """Create initial clause alignments and title diagnostics."""
    result: list[ClauseAlignment] = []
    for entry in expected:
        clause = entry.clause
        clause_id = clause.id.value
        candidate = selected.get(clause_id)
        if candidate is None:
            result.append(
                ClauseAlignment(
                    clause_id=clause_id,
                    expected_reference=clause.reference.clause,
                    status=AlignmentStatus.MISSING,
                )
            )
            issues.append(
                AlignmentIssue(
                    code="MISSING_REFERENCE",
                    clause_ids=(clause_id,),
                    message=(
                        f"No monotone candidate was selected for {clause.reference.clause!r}."
                    ),
                )
            )
            continue
        status = status_for_kind(candidate.match_kind)
        result.append(
            ClauseAlignment(
                clause_id=clause_id,
                expected_reference=clause.reference.clause,
                candidate_item_id=candidate.item_id,
                status=status,
                match_kind=candidate.match_kind,
                confidence=candidate.confidence,
                start_sequence_number=candidate.sequence_number,
                observed_title=(
                    candidate.title_remainder
                    if candidate.remainder_kind is CandidateRemainderKind.TITLE
                    else candidate.following_label
                ),
                observed_remainder=candidate.title_remainder,
                remainder_kind=candidate.remainder_kind,
                following_label_item_id=candidate.following_label_item_id,
                following_label=candidate.following_label,
                alternative_item_ids=alternatives.get(clause_id, ()),
            )
        )
        if (
            candidate.remainder_kind is CandidateRemainderKind.TITLE
            and candidate.title_remainder
            and clause.heading
        ):
            similarity = SequenceMatcher(
                None,
                candidate.title_remainder.casefold(),
                clause.heading.casefold(),
            ).ratio()
            if similarity < options.title_similarity_threshold:
                issues.append(
                    AlignmentIssue(
                        code="TITLE_MISMATCH",
                        clause_ids=(clause_id,),
                        item_ids=(candidate.item_id,),
                        message=(
                            "Observed title differs from the AtlasData title "
                            f"for {clause.reference.clause!r}."
                        ),
                    )
                )
    return result


def status_for_kind(kind: ReferenceMatchKind) -> AlignmentStatus:
    """Map a reference match kind to the initial alignment status."""
    if kind is ReferenceMatchKind.EXACT:
        return AlignmentStatus.EXACT
    if kind is ReferenceMatchKind.ANNEX:
        return AlignmentStatus.ANNEX
    return AlignmentStatus.NORMALIZED
