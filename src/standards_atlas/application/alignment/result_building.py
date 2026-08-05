"""Range construction, statistics, and stable alignment metadata helpers."""

from __future__ import annotations

import hashlib
import json
import re

from standards_atlas.application.model.alignment import (
    AlignmentIssue,
    AlignmentStatistics,
    AlignmentStatus,
    ClauseAlignment,
    UnassignedRange,
)
from standards_atlas.application.model.normalized_document import NormalizedExtractedDocument
from standards_atlas.domain.model import Clause, EngineeringDocument, Standard


def build_ranges(
    alignments: list[ClauseAlignment],
    normalized: NormalizedExtractedDocument,
    issues: list[AlignmentIssue],
) -> list[ClauseAlignment]:
    """Build non-overlapping source ranges from selected clause starts."""
    if not normalized.items:
        return alignments
    by_sequence = {item.sequence_number: item.id for item in normalized.items}
    document_end = max(by_sequence)
    starts = [
        (index, alignment.start_sequence_number)
        for index, alignment in enumerate(alignments)
        if alignment.start_sequence_number is not None
    ]
    result = list(alignments)
    for position, (index, start) in enumerate(starts):
        next_start = starts[position + 1][1] if position + 1 < len(starts) else None
        end = document_end if next_start is None else next_start - 1
        if end < start:
            issues.append(
                AlignmentIssue(
                    code="OVERLAPPING_CLAUSE_RANGE",
                    severity="error",
                    clause_ids=(result[index].clause_id,),
                    message="The calculated clause range overlaps the following clause.",
                )
            )
            end = start
        item_ids = tuple(
            by_sequence[sequence] for sequence in range(start, end + 1) if sequence in by_sequence
        )
        result[index] = result[index].model_copy(
            update={"end_sequence_number": end, "source_item_ids": item_ids}
        )
        if not item_ids:
            issues.append(
                AlignmentIssue(
                    code="EMPTY_CLAUSE_RANGE",
                    clause_ids=(result[index].clause_id,),
                    message="The calculated clause range contains no normalized items.",
                )
            )
    return result


def unassigned_ranges(
    alignments: list[ClauseAlignment],
    normalized: NormalizedExtractedDocument,
) -> list[UnassignedRange]:
    """Return contiguous normalized document ranges not assigned to clauses."""
    if not normalized.items:
        return []
    assigned = {
        sequence
        for alignment in alignments
        if alignment.start_sequence_number is not None and alignment.end_sequence_number is not None
        for sequence in range(
            alignment.start_sequence_number,
            alignment.end_sequence_number + 1,
        )
    }
    sequences = sorted(item.sequence_number for item in normalized.items)
    item_ids = {item.sequence_number: item.id for item in normalized.items}
    missing = [sequence for sequence in sequences if sequence not in assigned]
    if not missing:
        return []
    ranges: list[UnassignedRange] = []
    start = previous = missing[0]
    first_aligned = min(assigned) if assigned else None
    last_aligned = max(assigned) if assigned else None
    for sequence in missing[1:] + [None]:
        if sequence is not None and sequence == previous + 1:
            previous = sequence
            continue
        kind = (
            "front_matter"
            if first_aligned is None or previous < first_aligned
            else "back_matter"
            if last_aligned is not None and start > last_aligned
            else "between_clauses"
        )
        ranges.append(
            UnassignedRange(
                kind=kind,
                start_sequence_number=start,
                end_sequence_number=previous,
                source_item_ids=tuple(
                    item_ids[value] for value in range(start, previous + 1) if value in item_ids
                ),
            )
        )
        if sequence is not None:
            start = previous = sequence
    return ranges


def alignment_statistics(
    alignments: list[ClauseAlignment],
    unassigned: list[UnassignedRange],
) -> AlignmentStatistics:
    """Aggregate alignment status counts for result metadata."""
    counts = {status: 0 for status in AlignmentStatus}
    for alignment in alignments:
        counts[alignment.status] += 1
    return AlignmentStatistics(
        expected_clauses=len(alignments),
        exact_matches=counts[AlignmentStatus.EXACT],
        normalized_matches=counts[AlignmentStatus.NORMALIZED],
        annex_matches=counts[AlignmentStatus.ANNEX],
        low_confidence_matches=counts[AlignmentStatus.LOW_CONFIDENCE],
        inferred_matches=counts[AlignmentStatus.SEQUENCE_INFERRED],
        ambiguous=counts[AlignmentStatus.AMBIGUOUS],
        missing=counts[AlignmentStatus.MISSING],
        conflicting=counts[AlignmentStatus.CONFLICTING],
        unassigned_ranges=len(unassigned),
    )


def is_legacy_part_anchor(clause: Clause, document: EngineeringDocument) -> bool:
    """Identify AtlasData's synthetic clause 0 in derived standard-part views."""
    return (
        isinstance(document, Standard)
        and document.parent_key is not None
        and clause.reference.clause.strip() == "0"
    )


def model_hash(model: object) -> str:
    """Hash a Pydantic model while excluding volatile creation timestamps."""
    payload = model.model_dump(mode="json")
    payload.get("metadata", {}).pop("created_at", None)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def structure_hash(document: EngineeringDocument) -> str:
    """Hash the expected clause identity and hierarchy."""
    payload = [
        (
            clause.id.value,
            clause.reference.clause,
            clause.parent_id.value if clause.parent_id else None,
        )
        for clause in document.clauses
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def reference_sort_key(reference: str) -> tuple[tuple[int, int | str], ...]:
    """Return deterministic physical-document order for clause references."""
    parts = [part for part in re.split(r"[.\-]", reference.strip()) if part]
    key: list[tuple[int, int | str]] = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
            continue
        match = re.fullmatch(r"([A-Za-z]+)(\d*)", part)
        if match:
            key.append((1, match.group(1).casefold()))
            if match.group(2):
                key.append((0, int(match.group(2))))
        else:
            key.append((2, part.casefold()))
    return tuple(key)
