"""Render alignment problems and source context as Markdown."""

from __future__ import annotations

from standards_atlas.application.model.alignment import AlignmentResult, AlignmentStatus
from standards_atlas.application.model.normalized_document import NormalizedExtractedDocument
from standards_atlas.application.model.reference_candidates import (
    ReferenceCandidateDocument,
    ReferenceCandidateStatus,
)
from standards_atlas.domain.model import EngineeringDocument


class AlignmentReviewRenderer:
    def render(
        self,
        automatic: AlignmentResult,
        normalized: NormalizedExtractedDocument,
        candidates: ReferenceCandidateDocument,
        engineering: EngineeringDocument,
        *,
        context_before: int = 2,
        context_after: int = 4,
    ) -> str:
        lines = [
            f"# Alignment Review: {automatic.source_id}",
            "",
            "## Summary",
            "",
            "| Status | Count |",
            "|---|---:|",
            f"| Missing | {automatic.metadata.statistics.missing} |",
            f"| Inferred | {automatic.metadata.statistics.inferred_matches} |",
            f"| Issues | {len(automatic.issues)} |",
            "",
        ]
        clause_by_id = {clause.id.value: clause for clause in engineering.clauses}
        item_by_sequence = {item.sequence_number: item for item in normalized.items}
        candidate_by_clause: dict[str, list] = {}
        for candidate in candidates.candidates:
            for clause_id in candidate.expected_clause_ids:
                candidate_by_clause.setdefault(clause_id, []).append(candidate)

        for alignment in automatic.clauses:
            if alignment.status not in {
                AlignmentStatus.MISSING,
                AlignmentStatus.SEQUENCE_INFERRED,
                AlignmentStatus.AMBIGUOUS,
                AlignmentStatus.CONFLICTING,
            }:
                continue
            clause = clause_by_id[alignment.clause_id]
            lines.extend(
                [
                    f"## {alignment.status.value}: {alignment.expected_reference}",
                    "",
                    f"- Clause ID: `{alignment.clause_id}`",
                    f"- AtlasData title: {clause.heading or '(none)'}",
                    "",
                    "### Candidate alternatives",
                    "",
                ]
            )
            alternatives = candidate_by_clause.get(alignment.clause_id, [])
            if alternatives:
                for candidate in alternatives:
                    lines.append(
                        f"- `{candidate.item_id}` on sequence {candidate.sequence_number}: "
                        f"`{candidate.normalized_reference}` "
                        f"{candidate.title_remainder or candidate.following_label or ''}"
                    )
            else:
                lines.append("- No detected candidate.")
            center = alignment.start_sequence_number
            if center is None and alternatives:
                center = alternatives[0].sequence_number
            if center is not None:
                lines.extend(["", "### Normalized context", ""])
                start = max(0, center - context_before)
                end = center + context_after
                for sequence in range(start, end + 1):
                    item = item_by_sequence.get(sequence)
                    if item is None:
                        continue
                    text = getattr(item, "text", None) or getattr(item, "code", None)
                    lines.extend(
                        [
                            f"#### Item `{item.id}` (sequence {sequence}, type `{item.type}`)",
                            "",
                            "```text",
                            text or f"[{item.type}]",
                            "```",
                            "",
                        ]
                    )
            override_candidate_item_id = (
                alternatives[0].item_id if alternatives else "normalized:#/texts/"
            )
            lines.extend(
                [
                    "### Override example",
                    "",
                    "```yaml",
                    "- action: assign",
                    f"  clause_id: {alignment.clause_id}",
                    f"  candidate_item_id: {override_candidate_item_id}",
                    "  comment: <review decision>",
                    "```",
                    "",
                ]
            )

        unexpected = [
            candidate
            for candidate in candidates.candidates
            if candidate.status is ReferenceCandidateStatus.UNEXPECTED
        ]
        if unexpected:
            lines.extend(["## Unexpected candidates", ""])
            for candidate in unexpected:
                lines.extend(
                    [
                        f"### `{candidate.normalized_reference}` at item `{candidate.item_id}`",
                        "",
                        f"Observed remainder: {candidate.title_remainder or '(none)'}",
                        "",
                        "```yaml",
                        "- action: ignore_candidate",
                        f"  candidate_item_id: {candidate.item_id}",
                        "  reason: not_a_clause_reference",
                        "```",
                        "",
                    ]
                )
        return "\n".join(lines).rstrip() + "\n"
