"""Monotone alignment of reference candidates with AtlasData clauses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from standards_atlas import __version__
from standards_atlas.application.alignment.matching import (
    candidate_index,
    candidate_score,
    initial_alignments,
    select_monotone,
)
from standards_atlas.application.alignment.matching import (
    status_for_kind as _matching_status_for_kind,
)
from standards_atlas.application.alignment.recovery import (
    infer_single_gaps,
    recover_candidate_from_normalized_items,
    recover_low_confidence_candidates,
)
from standards_atlas.application.alignment.result_building import (
    alignment_statistics,
    build_ranges,
    is_legacy_part_anchor,
    model_hash,
    reference_sort_key,
    structure_hash,
    unassigned_ranges,
)
from standards_atlas.application.model.alignment import (
    AlignmentIssue,
    AlignmentMetadata,
    AlignmentOptions,
    AlignmentResult,
    AlignmentStatus,
)
from standards_atlas.application.model.normalized_document import NormalizedExtractedDocument
from standards_atlas.application.model.reference_candidates import (
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
        alignable_clauses = tuple(
            clause
            for clause in engineering.clauses
            if not _is_legacy_part_anchor(clause, engineering)
        )
        ordered_clauses = sorted(
            alignable_clauses,
            key=lambda clause: _reference_sort_key(clause.reference.clause),
        )
        expected = tuple(
            _ExpectedClause(clause=clause, index=index)
            for index, clause in enumerate(ordered_clauses)
        )
        candidate_index = self._candidate_index(candidates)
        selected, alternatives, issues = self._select_monotone(expected, candidate_index)
        alignments = self._initial_alignments(expected, selected, alternatives, issues, options)
        alignments = self._recover_low_confidence_candidates(
            alignments,
            expected,
            candidate_index,
            alternatives,
            normalized,
            options,
            issues,
        )
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
        return candidate_index(document)

    @staticmethod
    def _select_monotone(expected, candidate_index):
        return select_monotone(expected, candidate_index)

    @staticmethod
    def _candidate_score(candidate: ReferenceCandidate, clause: Clause) -> float:
        return candidate_score(candidate, clause)

    @staticmethod
    def _initial_alignments(expected, selected, alternatives, issues, options):
        return initial_alignments(expected, selected, alternatives, issues, options)

    @staticmethod
    def _recover_low_confidence_candidates(
        alignments,
        expected,
        candidate_index,
        alternatives,
        normalized,
        options,
        issues,
    ):
        return recover_low_confidence_candidates(
            alignments,
            expected,
            candidate_index,
            alternatives,
            normalized,
            options,
            issues,
        )

    @staticmethod
    def _recover_candidate_from_normalized_items(
        reference: str,
        normalized: NormalizedExtractedDocument,
        previous_start: int,
        following_start: int | None,
    ) -> ReferenceCandidate | None:
        return recover_candidate_from_normalized_items(
            reference,
            normalized,
            previous_start,
            following_start,
        )

    @staticmethod
    def _infer_single_gaps(alignments, normalized, options, issues):
        return infer_single_gaps(alignments, normalized, options, issues)

    @staticmethod
    def _build_ranges(alignments, normalized, issues):
        return build_ranges(alignments, normalized, issues)

    @staticmethod
    def _unassigned_ranges(alignments, normalized):
        return unassigned_ranges(alignments, normalized)

    @staticmethod
    def _statistics(alignments, unassigned):
        return alignment_statistics(alignments, unassigned)


def _is_legacy_part_anchor(clause: Clause, document: EngineeringDocument) -> bool:
    return is_legacy_part_anchor(clause, document)


def _status_for_kind(kind: ReferenceMatchKind) -> AlignmentStatus:
    return _matching_status_for_kind(kind)


def _hash_model(model) -> str:
    return model_hash(model)


def _structure_hash(document: EngineeringDocument) -> str:
    return structure_hash(document)


def _reference_sort_key(reference: str) -> tuple[tuple[int, int | str], ...]:
    return reference_sort_key(reference)
