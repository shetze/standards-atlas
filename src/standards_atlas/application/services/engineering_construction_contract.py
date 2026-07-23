"""Validate the closed construction boundary before EngineeringDocument creation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from standards_atlas.adapters.alignment_review import AlignmentReviewRepository
from standards_atlas.application.model.alignment import AlignmentResult
from standards_atlas.application.model.engineering_construction import (
    ConstructionCoverage,
    ConstructionDiagnostic,
    EngineeringConstructionContract,
)
from standards_atlas.application.model.normalized_document import (
    NormalizedExtractedDocument,
    NormalizedHeading,
)


class EngineeringConstructionContractValidator:
    """Check alignment completeness, freshness and item-level traceability."""

    def validate(
        self,
        normalized: NormalizedExtractedDocument,
        alignment: AlignmentResult,
        automatic_alignment: AlignmentResult,
        *,
        reviewed_alignment_used: bool,
        reviewed_integrity_valid: bool = True,
        reviewed_integrity_message: str | None = None,
    ) -> EngineeringConstructionContract:
        diagnostics: list[ConstructionDiagnostic] = []
        item_by_sequence = {item.sequence_number: item for item in normalized.items}
        item_ids = {item.id for item in normalized.items}
        assigned: Counter[str] = Counter()
        structural: set[str] = set()
        following_labels: set[str] = set()

        automatic_hash = AlignmentReviewRepository.hash_alignment(automatic_alignment)
        alignment_hash = AlignmentReviewRepository.hash_alignment(alignment)
        normalized_hash = _hash_model(normalized)

        if alignment.metadata.normalized_document_hash != normalized_hash:
            diagnostics.append(
                ConstructionDiagnostic(
                    code="stale_alignment",
                    severity="error",
                    message="Alignment was created for a different normalized document hash.",
                )
            )

        reviewed_unchanged = reviewed_integrity_valid
        if reviewed_alignment_used:
            reviewed_unchanged = reviewed_unchanged and (
                alignment.metadata.normalized_document_hash
                == automatic_alignment.metadata.normalized_document_hash
                and alignment.metadata.candidate_document_hash
                == automatic_alignment.metadata.candidate_document_hash
                and alignment.metadata.expected_structure_hash
                == automatic_alignment.metadata.expected_structure_hash
                and alignment.metadata.alignment_version
                == automatic_alignment.metadata.alignment_version
            )
            if not reviewed_unchanged:
                diagnostics.append(
                    ConstructionDiagnostic(
                        code="reviewed_alignment_stale",
                        severity="error",
                        message=(
                            reviewed_integrity_message
                            or (
                                "Reviewed alignment no longer matches the automatic "
                                "alignment inputs."
                            )
                        ),
                    )
                )

        seen_clause_ids: Counter[str] = Counter(entry.clause_id for entry in alignment.clauses)
        duplicates = tuple(sorted(key for key, count in seen_clause_ids.items() if count > 1))
        if duplicates:
            diagnostics.append(
                ConstructionDiagnostic(
                    code="duplicate_clause_alignment",
                    severity="error",
                    message="Clauses have more than one alignment range.",
                    clause_ids=duplicates,
                )
            )

        ranges: list[tuple[int, int, str]] = []
        for entry in alignment.clauses:
            start = entry.start_sequence_number
            end = entry.end_sequence_number
            if start is None and end is None:
                continue
            if start is None or end is None or start > end:
                diagnostics.append(
                    ConstructionDiagnostic(
                        code="invalid_clause_range",
                        severity="error",
                        message="Clause alignment has an incomplete or inverted range.",
                        clause_ids=(entry.clause_id,),
                    )
                )
                continue
            ranges.append((start, end, entry.clause_id))
            for sequence in range(start, end + 1):
                item = item_by_sequence.get(sequence)
                if item is not None:
                    assigned[item.id] += 1
            first = item_by_sequence.get(start)
            if isinstance(first, NormalizedHeading):
                structural.add(first.id)
            if entry.following_label_item_id:
                label_id = entry.following_label_item_id
                if label_id not in item_ids:
                    diagnostics.append(
                        ConstructionDiagnostic(
                            code="missing_following_label",
                            severity="error",
                            message="following_label_item_id does not identify an active item.",
                            clause_ids=(entry.clause_id,),
                            normalized_item_ids=(label_id,),
                        )
                    )
                elif not (start <= _sequence_for(label_id, normalized) <= end):
                    diagnostics.append(
                        ConstructionDiagnostic(
                            code="following_label_outside_range",
                            severity="error",
                            message="following_label_item_id lies outside its clause range.",
                            clause_ids=(entry.clause_id,),
                            normalized_item_ids=(label_id,),
                        )
                    )
                else:
                    following_labels.add(label_id)

        for (_, previous_end, previous_clause), (start, _, clause) in zip(
            sorted(ranges), sorted(ranges)[1:], strict=False
        ):
            if start <= previous_end:
                diagnostics.append(
                    ConstructionDiagnostic(
                        code="overlapping_clause_ranges",
                        severity="error",
                        message="Clause alignment ranges overlap.",
                        clause_ids=(previous_clause, clause),
                    )
                )

        overlaps = tuple(sorted(item_id for item_id, count in assigned.items() if count > 1))
        if overlaps:
            diagnostics.append(
                ConstructionDiagnostic(
                    code="items_assigned_multiple_times",
                    severity="error",
                    message="Active normalized items are assigned to multiple clauses.",
                    normalized_item_ids=overlaps,
                )
            )

        classified_unassigned: set[str] = set()
        counts = {"front_matter": 0, "between_clauses": 0, "back_matter": 0}
        for value in alignment.unassigned_ranges:
            for sequence in range(value.start_sequence_number, value.end_sequence_number + 1):
                item = item_by_sequence.get(sequence)
                if item is not None:
                    classified_unassigned.add(item.id)
                    counts[value.kind] += 1

        unassigned = item_ids - set(assigned) - classified_unassigned
        if unassigned:
            diagnostics.append(
                ConstructionDiagnostic(
                    code="unaccounted_normalized_items",
                    severity="error",
                    message=(
                        "Active normalized items are neither assigned to a clause nor classified "
                        "as front matter, back matter or an inter-clause range."
                    ),
                    normalized_item_ids=tuple(sorted(unassigned)),
                )
            )

        coverage = ConstructionCoverage(
            active_items=len(item_ids),
            assigned_items=len(set(assigned)),
            structural_heading_items=len(structural),
            following_label_items=len(following_labels),
            front_matter_items=counts["front_matter"],
            between_clause_items=counts["between_clauses"],
            back_matter_items=counts["back_matter"],
            unassigned_items=len(unassigned),
        )
        return EngineeringConstructionContract(
            valid=not any(item.severity == "error" for item in diagnostics),
            normalized_document_hash=normalized_hash,
            alignment_hash=alignment_hash,
            automatic_alignment_hash=automatic_hash,
            reviewed_alignment_used=reviewed_alignment_used,
            reviewed_alignment_unchanged=reviewed_unchanged,
            coverage=coverage,
            diagnostics=tuple(diagnostics),
        )


def _sequence_for(item_id: str, document: NormalizedExtractedDocument) -> int:
    return next(item.sequence_number for item in document.items if item.id == item_id)


def _hash_model(model) -> str:
    payload = model.model_dump(mode="json")
    payload.get("metadata", {}).pop("created_at", None)
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
