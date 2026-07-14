"""Validate and apply manual decisions to automatic alignment results."""

from __future__ import annotations

from standards_atlas.application.model.alignment import (
    AlignmentIssue,
    AlignmentResult,
    AlignmentStatistics,
    AlignmentStatus,
)
from standards_atlas.application.model.alignment_review import (
    AlignmentOverrideDocument,
    AssignOverride,
    DefineRangeOverride,
    IgnoreCandidateOverride,
    MarkMissingOverride,
    OverrideValidationIssue,
    OverrideValidationResult,
    SetFollowingLabelOverride,
    SetHeadingLevelOverride,
    SetObservedHeadingOverride,
    SetRemainderKindOverride,
)
from standards_atlas.application.model.normalized_document import NormalizedExtractedDocument
from standards_atlas.application.model.reference_candidates import (
    CandidateRemainderKind,
    ReferenceCandidateDocument,
    ReferenceMatchKind,
)
from standards_atlas.domain.model import EngineeringDocument


class AlignmentOverrideEngine:
    """Apply validated manual decisions without changing automatic artefacts."""

    def validate(
        self,
        overrides: AlignmentOverrideDocument,
        automatic: AlignmentResult,
        normalized: NormalizedExtractedDocument,
        candidates: ReferenceCandidateDocument,
        engineering: EngineeringDocument,
    ) -> OverrideValidationResult:
        clause_ids = {clause.id.value for clause in engineering.clauses}
        item_ids = {item.id for item in normalized.items}
        candidate_ids = {candidate.item_id for candidate in candidates.candidates}
        assignable_ids = item_ids | candidate_ids
        issues: list[OverrideValidationIssue] = []
        assigned_clauses: set[str] = set()
        assigned_candidates: set[str] = set()
        for index, override in enumerate(overrides.overrides):
            clause_id = getattr(override, "clause_id", None)
            if clause_id is not None and clause_id not in clause_ids:
                issues.append(
                    self._issue(index, "UNKNOWN_CLAUSE", f"Unknown clause ID {clause_id!r}.")
                )
            candidate_id = getattr(override, "candidate_item_id", None)
            if candidate_id is not None and candidate_id not in assignable_ids:
                issues.append(
                    self._issue(
                        index,
                        "UNKNOWN_CANDIDATE",
                        f"Unknown candidate or normalized item {candidate_id!r}.",
                    )
                )
            if isinstance(override, AssignOverride):
                if override.clause_id in assigned_clauses:
                    issues.append(
                        self._issue(index, "DUPLICATE_CLAUSE_ASSIGNMENT", "Clause assigned twice.")
                    )
                if override.candidate_item_id in assigned_candidates:
                    issues.append(
                        self._issue(
                            index,
                            "DUPLICATE_CANDIDATE_ASSIGNMENT",
                            "Candidate assigned twice.",
                        )
                    )
                assigned_clauses.add(override.clause_id)
                assigned_candidates.add(override.candidate_item_id)
            if isinstance(override, DefineRangeOverride):
                if override.start_item_id not in item_ids or override.end_item_id not in item_ids:
                    issues.append(
                        self._issue(index, "UNKNOWN_RANGE_ITEM", "Range item does not exist.")
                    )
                else:
                    sequences = {item.id: item.sequence_number for item in normalized.items}
                    if sequences[override.start_item_id] > sequences[override.end_item_id]:
                        issues.append(
                            self._issue(index, "REVERSED_RANGE", "Range start follows range end.")
                        )
            if isinstance(override, SetFollowingLabelOverride):
                if override.following_label_item_id not in item_ids:
                    issues.append(
                        self._issue(
                            index,
                            "UNKNOWN_LABEL_ITEM",
                            "Following label item does not exist.",
                        )
                    )
        return OverrideValidationResult(valid=not issues, issues=tuple(issues))

    def apply(
        self,
        overrides: AlignmentOverrideDocument,
        automatic: AlignmentResult,
        normalized: NormalizedExtractedDocument,
        candidates: ReferenceCandidateDocument,
        engineering: EngineeringDocument,
    ) -> AlignmentResult:
        validation = self.validate(overrides, automatic, normalized, candidates, engineering)
        if not validation.valid:
            messages = "; ".join(issue.message for issue in validation.issues)
            raise ValueError(f"Invalid alignment overrides: {messages}")
        clauses = {clause.clause_id: clause for clause in automatic.clauses}
        candidate_by_id = {candidate.item_id: candidate for candidate in candidates.candidates}
        item_by_id = {item.id: item for item in normalized.items}
        ignored: set[str] = set()
        manual_ranges: dict[str, tuple[int, int]] = {}
        issues = [
            issue
            for issue in automatic.issues
            if issue.code not in {"MISSING_REFERENCE", "INFERRED_REFERENCE"}
        ]

        for override in overrides.overrides:
            if isinstance(override, IgnoreCandidateOverride):
                ignored.add(override.candidate_item_id)
                for clause_id, clause in list(clauses.items()):
                    if clause.candidate_item_id == override.candidate_item_id:
                        clauses[clause_id] = clause.model_copy(
                            update={
                                "status": AlignmentStatus.MISSING,
                                "candidate_item_id": None,
                                "confidence": None,
                                "start_sequence_number": None,
                                "end_sequence_number": None,
                                "source_item_ids": (),
                            }
                        )
            elif isinstance(override, AssignOverride):
                existing = clauses[override.clause_id]
                candidate = candidate_by_id.get(override.candidate_item_id)
                if candidate is not None:
                    update = {
                        "candidate_item_id": candidate.item_id,
                        "status": AlignmentStatus.MANUAL,
                        "match_kind": candidate.match_kind,
                        "confidence": 1.0,
                        "start_sequence_number": candidate.sequence_number,
                        "observed_title": candidate.following_label or candidate.title_remainder,
                        "observed_remainder": candidate.title_remainder,
                        "remainder_kind": candidate.remainder_kind,
                        "following_label_item_id": candidate.following_label_item_id,
                        "following_label": candidate.following_label,
                    }
                else:
                    item = item_by_id[override.candidate_item_id]
                    update = {
                        "candidate_item_id": item.id,
                        "status": AlignmentStatus.MANUAL,
                        "match_kind": ReferenceMatchKind.INLINE,
                        "confidence": 1.0,
                        "start_sequence_number": item.sequence_number,
                        "observed_title": None,
                        "observed_remainder": None,
                        "remainder_kind": CandidateRemainderKind.UNKNOWN,
                    }
                clauses[override.clause_id] = existing.model_copy(update=update)
            elif isinstance(override, MarkMissingOverride):
                existing = clauses[override.clause_id]
                clauses[override.clause_id] = existing.model_copy(
                    update={
                        "status": AlignmentStatus.MANUAL,
                        "candidate_item_id": None,
                        "confidence": 1.0,
                        "start_sequence_number": None,
                        "end_sequence_number": None,
                        "source_item_ids": (),
                    }
                )
            elif isinstance(override, DefineRangeOverride):
                manual_ranges[override.clause_id] = (
                    item_by_id[override.start_item_id].sequence_number,
                    item_by_id[override.end_item_id].sequence_number,
                )
            elif isinstance(override, SetRemainderKindOverride):
                candidate = candidate_by_id.get(override.candidate_item_id)
                if candidate is not None:
                    candidate_by_id[override.candidate_item_id] = candidate.model_copy(
                        update={"remainder_kind": override.remainder_kind}
                    )
            elif isinstance(override, SetFollowingLabelOverride):
                candidate = candidate_by_id.get(override.candidate_item_id)
                if candidate is not None:
                    label_item = item_by_id[override.following_label_item_id]
                    label = getattr(label_item, "text", None)
                    candidate_by_id[override.candidate_item_id] = candidate.model_copy(
                        update={
                            "following_label_item_id": override.following_label_item_id,
                            "following_label": label,
                        }
                    )
            elif isinstance(override, SetObservedHeadingOverride):
                existing = clauses[override.clause_id]
                clauses[override.clause_id] = existing.model_copy(
                    update={"observed_title": override.heading}
                )
            elif isinstance(override, SetHeadingLevelOverride):
                existing = clauses[override.clause_id]
                clauses[override.clause_id] = existing.model_copy(
                    update={"manual_heading_level": override.level}
                )

        ordered = [clauses[clause.clause_id] for clause in automatic.clauses]
        ordered = self._rebuild_ranges(ordered, normalized, manual_ranges)
        for clause in ordered:
            if clause.status is AlignmentStatus.MISSING:
                issues.append(
                    AlignmentIssue(
                        code="MISSING_REFERENCE",
                        clause_ids=(clause.clause_id,),
                        message=f"No reviewed alignment exists for {clause.expected_reference!r}.",
                    )
                )
        stats = self._statistics(ordered, automatic.metadata.statistics.unassigned_ranges)
        metadata = automatic.metadata.model_copy(update={"statistics": stats})
        return automatic.model_copy(
            update={"clauses": tuple(ordered), "issues": tuple(issues), "metadata": metadata}
        )

    @staticmethod
    def _rebuild_ranges(clauses, normalized, manual_ranges):
        sequence_to_id = {item.sequence_number: item.id for item in normalized.items}
        document_end = max(sequence_to_id, default=-1)
        starts = [
            (index, clause.start_sequence_number)
            for index, clause in enumerate(clauses)
            if clause.start_sequence_number is not None
        ]
        result = list(clauses)
        for position, (index, start) in enumerate(starts):
            clause = result[index]
            if clause.clause_id in manual_ranges:
                start, end = manual_ranges[clause.clause_id]
            else:
                next_start = starts[position + 1][1] if position + 1 < len(starts) else None
                end = document_end if next_start is None else next_start - 1
            ids = tuple(
                sequence_to_id[number]
                for number in range(start, end + 1)
                if number in sequence_to_id
            )
            result[index] = clause.model_copy(
                update={
                    "start_sequence_number": start,
                    "end_sequence_number": end,
                    "source_item_ids": ids,
                }
            )
        return result

    @staticmethod
    def _statistics(clauses, unassigned_ranges):
        return AlignmentStatistics(
            expected_clauses=len(clauses),
            exact_matches=sum(c.status is AlignmentStatus.EXACT for c in clauses),
            normalized_matches=sum(c.status is AlignmentStatus.NORMALIZED for c in clauses),
            annex_matches=sum(c.status is AlignmentStatus.ANNEX for c in clauses),
            inferred_matches=sum(c.status is AlignmentStatus.SEQUENCE_INFERRED for c in clauses),
            ambiguous=sum(c.status is AlignmentStatus.AMBIGUOUS for c in clauses),
            missing=sum(c.status is AlignmentStatus.MISSING for c in clauses),
            conflicting=sum(c.status is AlignmentStatus.CONFLICTING for c in clauses),
            unassigned_ranges=unassigned_ranges,
        )

    @staticmethod
    def _issue(index: int, code: str, message: str) -> OverrideValidationIssue:
        return OverrideValidationIssue(code=code, override_index=index, message=message)
