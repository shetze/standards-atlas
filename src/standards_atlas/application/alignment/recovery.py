"""Conservative recovery of missing clause alignment anchors."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from standards_atlas.application.alignment.matching import candidate_score
from standards_atlas.application.model.alignment import (
    AlignmentIssue,
    AlignmentOptions,
    AlignmentStatus,
    ClauseAlignment,
)
from standards_atlas.application.model.normalized_document import (
    NormalizedExtractedDocument,
    NormalizedHeading,
    NormalizedText,
)
from standards_atlas.application.model.reference_candidates import (
    CandidateRemainderKind,
    ReferenceCandidate,
    ReferenceCandidateStatus,
    ReferenceMatchKind,
)
from standards_atlas.domain.model import Clause


class ExpectedClause(Protocol):
    """Structural view required by recovery."""

    clause: Clause
    index: int


def recover_low_confidence_candidates(
    alignments: Sequence[ClauseAlignment],
    expected: Sequence[ExpectedClause],
    candidate_index: dict[str, list[ReferenceCandidate]],
    alternatives: dict[str, tuple[str, ...]],
    normalized: NormalizedExtractedDocument,
    options: AlignmentOptions,
    issues: list[AlignmentIssue],
) -> list[ClauseAlignment]:
    """Recover missing starts from candidates bounded by aligned neighbours."""
    if not options.recover_low_confidence_candidates:
        return alignments
    result = list(alignments)
    for index, current in enumerate(result):
        if current.status is not AlignmentStatus.MISSING:
            continue
        previous_start = next(
            (
                result[position].start_sequence_number
                for position in range(index - 1, -1, -1)
                if result[position].start_sequence_number is not None
            ),
            -1,
        )
        following_start = next(
            (
                result[position].start_sequence_number
                for position in range(index + 1, len(result))
                if result[position].start_sequence_number is not None
            ),
            None,
        )
        clause = expected[index].clause
        bounded = [
            candidate
            for candidate in candidate_index.get(clause.id.value, ())
            if candidate.sequence_number > previous_start
            and (following_start is None or candidate.sequence_number < following_start)
        ]
        candidate = (
            max(
                bounded,
                key=lambda value: (
                    candidate_score(value, clause),
                    -value.sequence_number,
                ),
            )
            if bounded
            else recover_candidate_from_normalized_items(
                clause.reference.clause,
                normalized,
                previous_start,
                following_start,
            )
        )
        if candidate is None:
            continue
        result[index] = current.model_copy(
            update={
                "candidate_item_id": candidate.item_id,
                "status": AlignmentStatus.LOW_CONFIDENCE,
                "match_kind": candidate.match_kind,
                "confidence": candidate.confidence,
                "start_sequence_number": candidate.sequence_number,
                "observed_title": (
                    candidate.title_remainder
                    if candidate.remainder_kind is CandidateRemainderKind.TITLE
                    else candidate.following_label
                ),
                "observed_remainder": candidate.title_remainder,
                "remainder_kind": candidate.remainder_kind,
                "following_label_item_id": candidate.following_label_item_id,
                "following_label": candidate.following_label,
                "alternative_item_ids": alternatives.get(clause.id.value, ()),
            }
        )
        issues[:] = [
            issue
            for issue in issues
            if not (issue.code == "MISSING_REFERENCE" and clause.id.value in issue.clause_ids)
        ]
        issues.append(
            AlignmentIssue(
                code="LOW_CONFIDENCE_REFERENCE",
                severity="warning",
                clause_ids=(clause.id.value,),
                item_ids=(candidate.item_id,),
                message=(
                    f"Recovered {clause.reference.clause!r} from a candidate "
                    "between established neighbouring clause anchors."
                ),
            )
        )
    return result


def recover_candidate_from_normalized_items(
    reference: str,
    normalized: NormalizedExtractedDocument,
    previous_start: int,
    following_start: int | None,
) -> ReferenceCandidate | None:
    """Find one bounded clause-number start missed by candidate detection."""
    escaped_parts = [re.escape(part) for part in reference.strip().split(".")]
    reference_pattern = r"\s*[.]\s*".join(escaped_parts)
    pattern = re.compile(
        rf"^\s*(?:[-–—•]\s*)?(?P<ref>{reference_pattern})(?:[.]?)"
        rf"(?=\s|$)(?P<remainder>.*)$",
        re.IGNORECASE,
    )
    matches: list[ReferenceCandidate] = []
    for item in normalized.items:
        if item.sequence_number <= previous_start:
            continue
        if following_start is not None and item.sequence_number >= following_start:
            continue
        if not isinstance(item, (NormalizedHeading, NormalizedText)):
            continue
        match = pattern.match(item.text)
        if match is None:
            continue
        remainder = match.group("remainder").strip()
        is_heading = isinstance(item, NormalizedHeading)
        matches.append(
            ReferenceCandidate(
                item_id=item.id,
                sequence_number=item.sequence_number,
                raw_reference=match.group("ref"),
                normalized_reference=reference,
                title_remainder=remainder or None,
                remainder_kind=(
                    CandidateRemainderKind.TITLE
                    if remainder and is_heading
                    else CandidateRemainderKind.CONTENT
                    if remainder
                    else CandidateRemainderKind.UNKNOWN
                ),
                match_kind=ReferenceMatchKind.INLINE,
                status=ReferenceCandidateStatus.EXPECTED,
                confidence=0.60,
                expected_clause_ids=(),
            )
        )
    return matches[0] if len(matches) == 1 else None


def infer_single_gaps(
    alignments: Sequence[ClauseAlignment],
    normalized: NormalizedExtractedDocument,
    options: AlignmentOptions,
    issues: list[AlignmentIssue],
) -> list[ClauseAlignment]:
    """Infer one missing start bounded by directly aligned neighbours."""
    if not options.infer_single_missing_clause:
        return alignments
    result = list(alignments)
    for index in range(1, len(result) - 1):
        current = result[index]
        previous = result[index - 1]
        following = result[index + 1]
        if current.status is not AlignmentStatus.MISSING:
            continue
        if previous.start_sequence_number is None or following.start_sequence_number is None:
            continue
        start = previous.start_sequence_number + 1
        end = following.start_sequence_number - 1
        if start > end:
            continue
        result[index] = current.model_copy(
            update={
                "status": AlignmentStatus.SEQUENCE_INFERRED,
                "confidence": 0.4,
                "start_sequence_number": start,
            }
        )
        issues.append(
            AlignmentIssue(
                code="INFERRED_REFERENCE",
                severity="info",
                clause_ids=(current.clause_id,),
                message=(
                    f"The start of {current.expected_reference!r} was inferred "
                    "from its aligned neighbours."
                ),
            )
        )
    return result
