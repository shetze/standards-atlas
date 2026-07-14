"""Monotone alignment of reference candidates with AtlasData clauses."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher

from standards_atlas import __version__
from standards_atlas.application.model.alignment import (
    AlignmentIssue,
    AlignmentMetadata,
    AlignmentOptions,
    AlignmentResult,
    AlignmentStatistics,
    AlignmentStatus,
    ClauseAlignment,
    UnassignedRange,
)
from standards_atlas.application.model.normalized_document import NormalizedExtractedDocument
from standards_atlas.application.model.reference_candidates import (
    CandidateRemainderKind,
    ReferenceCandidate,
    ReferenceCandidateDocument,
    ReferenceMatchKind,
)
from standards_atlas.domain.model import Clause, EngineeringDocument


@dataclass(frozen=True)
class _ExpectedClause:
    clause: Clause
    index: int


class AlignmentEngine:
    """Create deterministic clause starts and ranges without mutating inputs."""

    def align(
        self,
        normalized: NormalizedExtractedDocument,
        candidates: ReferenceCandidateDocument,
        engineering: EngineeringDocument,
        options: AlignmentOptions | None = None,
    ) -> AlignmentResult:
        options = options or AlignmentOptions()
        expected = tuple(
            _ExpectedClause(clause=clause, index=index)
            for index, clause in enumerate(engineering.clauses)
        )
        candidate_index = self._candidate_index(candidates)
        selected, alternatives, issues = self._select_monotone(expected, candidate_index)
        alignments = self._initial_alignments(expected, selected, alternatives, issues, options)
        alignments = self._infer_single_gaps(alignments, normalized, options, issues)
        alignments = self._build_ranges(alignments, normalized, issues)
        unassigned = self._unassigned_ranges(alignments, normalized)
        if unassigned:
            issues.append(
                AlignmentIssue(
                    code="UNASSIGNED_CONTENT",
                    severity="info",
                    item_ids=tuple(
                        item_id
                        for item_range in unassigned
                        for item_id in item_range.source_item_ids
                    ),
                    message=f"{len(unassigned)} document range(s) are not assigned to clauses.",
                )
            )
        statistics = self._statistics(alignments, unassigned)
        return AlignmentResult(
            source_id=normalized.source_id,
            clauses=tuple(alignments),
            unassigned_ranges=tuple(unassigned),
            issues=tuple(issues),
            metadata=AlignmentMetadata(
                alignment_version=__version__,
                normalized_document_hash=_hash_model(normalized),
                candidate_document_hash=_hash_model(candidates),
                expected_structure_hash=_structure_hash(engineering),
                created_at=datetime.now(UTC),
                options=options,
                statistics=statistics,
            ),
        )

    @staticmethod
    def _candidate_index(
        document: ReferenceCandidateDocument,
    ) -> dict[str, list[ReferenceCandidate]]:
        index: dict[str, list[ReferenceCandidate]] = {}
        for candidate in document.candidates:
            for clause_id in candidate.expected_clause_ids:
                index.setdefault(clause_id, []).append(candidate)
        for values in index.values():
            values.sort(key=lambda candidate: candidate.sequence_number)
        return index

    def _select_monotone(self, expected, candidate_index):
        selected: dict[str, ReferenceCandidate] = {}
        alternatives: dict[str, tuple[str, ...]] = {}
        issues: list[AlignmentIssue] = []
        last_sequence = -1
        for entry in expected:
            clause_id = entry.clause.id.value
            all_candidates = candidate_index.get(clause_id, [])
            eligible = [
                candidate
                for candidate in all_candidates
                if candidate.sequence_number > last_sequence
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
                    self._candidate_score(candidate, entry.clause),
                    -candidate.sequence_number,
                ),
            )
            selected[clause_id] = chosen
            last_sequence = chosen.sequence_number
            discarded = tuple(
                candidate.item_id
                for candidate in all_candidates
                if candidate.item_id != chosen.item_id
            )
            alternatives[clause_id] = discarded
            if discarded:
                issues.append(
                    AlignmentIssue(
                        code="DUPLICATE_REFERENCE",
                        clause_ids=(clause_id,),
                        item_ids=(chosen.item_id, *discarded),
                        message=(
                            f"Multiple candidates were found for "
                            f"{entry.clause.reference.clause!r}; one was selected."
                        ),
                    )
                )
        return selected, alternatives, issues

    @staticmethod
    def _candidate_score(candidate: ReferenceCandidate, clause: Clause) -> float:
        title_score = 0.0
        if (
            candidate.remainder_kind is CandidateRemainderKind.TITLE
            and candidate.title_remainder
            and clause.title
        ):
            title_score = SequenceMatcher(
                None,
                candidate.title_remainder.casefold(),
                clause.title.casefold(),
            ).ratio()
        kind_bonus = {
            ReferenceMatchKind.EXACT: 0.05,
            ReferenceMatchKind.ANNEX: 0.04,
            ReferenceMatchKind.NORMALIZED: 0.02,
            ReferenceMatchKind.INLINE: 0.0,
        }[candidate.match_kind]
        return candidate.confidence + kind_bonus + (0.1 * title_score)

    def _initial_alignments(self, expected, selected, alternatives, issues, options):
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
            status = _status_for_kind(candidate.match_kind)
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
                and clause.title
            ):
                similarity = SequenceMatcher(
                    None,
                    candidate.title_remainder.casefold(),
                    clause.title.casefold(),
                ).ratio()
                if similarity < options.title_similarity_threshold:
                    issues.append(
                        AlignmentIssue(
                            code="TITLE_MISMATCH",
                            clause_ids=(clause_id,),
                            item_ids=(candidate.item_id,),
                            message=(
                                f"Observed title differs from the AtlasData title "
                                f"for {clause.reference.clause!r}."
                            ),
                        )
                    )
        return result

    @staticmethod
    def _infer_single_gaps(alignments, normalized, options, issues):
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

    @staticmethod
    def _build_ranges(alignments, normalized, issues):
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
                by_sequence[sequence]
                for sequence in range(start, end + 1)
                if sequence in by_sequence
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

    @staticmethod
    def _unassigned_ranges(alignments, normalized):
        if not normalized.items:
            return []
        assigned = {
            sequence
            for alignment in alignments
            if alignment.start_sequence_number is not None
            and alignment.end_sequence_number is not None
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

    @staticmethod
    def _statistics(alignments, unassigned):
        counts = {status: 0 for status in AlignmentStatus}
        for alignment in alignments:
            counts[alignment.status] += 1
        return AlignmentStatistics(
            expected_clauses=len(alignments),
            exact_matches=counts[AlignmentStatus.EXACT],
            normalized_matches=counts[AlignmentStatus.NORMALIZED],
            annex_matches=counts[AlignmentStatus.ANNEX],
            inferred_matches=counts[AlignmentStatus.SEQUENCE_INFERRED],
            ambiguous=counts[AlignmentStatus.AMBIGUOUS],
            missing=counts[AlignmentStatus.MISSING],
            conflicting=counts[AlignmentStatus.CONFLICTING],
            unassigned_ranges=len(unassigned),
        )


def _status_for_kind(kind: ReferenceMatchKind) -> AlignmentStatus:
    if kind is ReferenceMatchKind.EXACT:
        return AlignmentStatus.EXACT
    if kind is ReferenceMatchKind.ANNEX:
        return AlignmentStatus.ANNEX
    return AlignmentStatus.NORMALIZED


def _hash_model(model) -> str:
    payload = model.model_dump(mode="json")
    payload.get("metadata", {}).pop("created_at", None)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _structure_hash(document: EngineeringDocument) -> str:
    payload = [
        (
            clause.id.value,
            clause.reference.clause,
            clause.parent_id.value if clause.parent_id else None,
        )
        for clause in document.clauses
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
