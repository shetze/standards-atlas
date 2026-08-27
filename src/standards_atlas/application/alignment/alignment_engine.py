"""Monotone alignment of reference candidates with AtlasData clauses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from standards_atlas import __version__
from standards_atlas.application.alignment.matching import (
    candidate_index,
    initial_alignments,
    select_monotone,
)
from standards_atlas.application.alignment.recovery import (
    infer_single_gaps,
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
)
from standards_atlas.application.model.normalized_document import NormalizedExtractedDocument
from standards_atlas.application.model.reference_candidates import (
    ReferenceCandidateDocument,
)
from standards_atlas.domain.model import Clause, ClauseType, EngineeringDocument


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
            if clause.clause_type is not ClauseType.TABLE
            and not is_legacy_part_anchor(clause, engineering)
        )
        ordered_clauses = sorted(
            alignable_clauses,
            key=lambda clause: reference_sort_key(clause.reference.clause),
        )
        expected = tuple(
            _ExpectedClause(clause=clause, index=index)
            for index, clause in enumerate(ordered_clauses)
        )
        indexed_candidates = candidate_index(candidates)
        selected, alternatives, issues = select_monotone(expected, indexed_candidates)
        alignments = initial_alignments(expected, selected, alternatives, issues, options)
        alignments = recover_low_confidence_candidates(
            alignments,
            expected,
            indexed_candidates,
            alternatives,
            normalized,
            options,
            issues,
        )
        alignments = infer_single_gaps(alignments, normalized, options, issues)
        alignments = build_ranges(alignments, normalized, issues)
        unassigned = unassigned_ranges(alignments, normalized)
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
        statistics = alignment_statistics(alignments, unassigned)
        return AlignmentResult(
            source_id=normalized.source_id,
            clauses=tuple(alignments),
            unassigned_ranges=tuple(unassigned),
            issues=tuple(issues),
            metadata=AlignmentMetadata(
                alignment_version=__version__,
                normalized_document_hash=model_hash(normalized),
                candidate_document_hash=model_hash(candidates),
                expected_structure_hash=structure_hash(engineering),
                created_at=datetime.now(UTC),
                options=options,
                statistics=statistics,
            ),
        )
