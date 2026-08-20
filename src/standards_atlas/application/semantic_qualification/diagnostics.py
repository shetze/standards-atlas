"""Diagnostic views for semantic qualification consensus results."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any

from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
)

_NONE = "none"
_NEAR_DUPLICATE_THRESHOLD = 0.92


def build_qualification_diagnostics(
    *, report: ConsensusReport, cascade_stages: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build non-normative diagnostics without changing qualification decisions."""

    applicability_conflicts = _applicability_conflict_diagnostics(report.clauses)
    model_fitness = _applicability_model_fitness(report.clauses)
    duplicates = _duplicate_diagnostics(report.clauses)
    multi_assertion = _multi_assertion_candidates(report.clauses)
    stage_contributions = _stage_contributions(cascade_stages)
    return {
        "applicability_conflicts": applicability_conflicts,
        "applicability_model_fitness": model_fitness,
        "duplicate_clusters": duplicates,
        "multi_applicability_assertion_candidates": multi_assertion,
        "stage_contributions": stage_contributions,
    }


def render_qualification_diagnostics_markdown(
    *, report: ConsensusReport, diagnostics: dict[str, Any]
) -> str:
    """Render compact diagnostics intended to guide taxonomy/model refinement."""

    conflicts = diagnostics["applicability_conflicts"]
    fitness = diagnostics["applicability_model_fitness"]
    duplicates = diagnostics["duplicate_clusters"]
    multi = diagnostics["multi_applicability_assertion_candidates"]
    stages = diagnostics["stage_contributions"]
    lines = [
        f"# Qualification diagnostics: {report.matrix_id}",
        "",
        "These diagnostics are observational only. They do not alter model weights, "
        "thresholds, consensus categories, or cascade resolution.",
        "",
        "## Applicability conflict clusters",
        "",
        f"- Clauses with applicability vote disagreement: `{conflicts['clause_count']}`",
        f"- Clauses with presence disagreement: `{conflicts['presence_disagreement_count']}`",
        f"- Clauses with subtype disagreement: `{conflicts['subtype_disagreement_count']}`",
        "",
        "| Votes observed | Clauses |",
        "| --- | ---: |",
    ]
    for item in conflicts["clusters"]:
        lines.append(f"| `{item['signature']}` | {item['count']} |")
    if not conflicts["clusters"]:
        lines.append("| none | 0 |")

    lines.extend(
        [
            "",
            "## Applicability model fitness signals",
            "",
            "`none` rate is shown separately for all voted clauses and for clauses with "
            "applicability disagreement. Agreement rates use only high-confidence "
            "unanimous/strong consensus as a reference signal; they are not accuracy scores.",
            "",
            "| Model | Votes | Present | None rate | Conflict votes | Conflict none rate | "
            "Presence agreement | Subtype agreement |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in fitness:
        lines.append(
            f"| `{item['model_id']}` | {item['vote_count']} | {item['present_count']} | "
            f"{item['none_rate']:.3f} | {item['conflict_vote_count']} | "
            f"{item['conflict_none_rate']:.3f} | "
            f"{_format_optional_rate(item['presence_reference_agreement_rate'])} | "
            f"{_format_optional_rate(item['subtype_reference_agreement_rate'])} |"
        )

    lines.extend(["", "## Cascade stage contributions", ""])
    if stages:
        lines.extend(
            [
                "| Stage | Entered | Remaining | Statement | Knowledge | Applicability | "
                "Role relation |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in stages:
            resolved = item["newly_resolved_counts"]
            lines.append(
                f"| `{item['stage_id']}` | {item['entered_clause_count']} | "
                f"{item['unresolved_clause_count']} | "
                f"{resolved.get('statement_function', 0)} | "
                f"{resolved.get('knowledge_kind', 0)} | "
                f"{resolved.get('applicability', 0)} | "
                f"{resolved.get('role_relation', 0)} |"
            )
    else:
        lines.append("No cascade stages were recorded.")

    lines.extend(
        [
            "",
            "## Duplicate and near-duplicate review clauses",
            "",
            f"- Exact duplicate clusters: `{duplicates['exact_cluster_count']}`",
            f"- Near-duplicate clusters: `{duplicates['near_cluster_count']}`",
        ]
    )
    for item in duplicates["clusters"]:
        refs = ", ".join(f"`{ref}`" for ref in item["references"])
        lines.append(f"- **{item['kind']}** ({item['size']}): {refs}")

    lines.extend(
        [
            "",
            "## Multiple applicability assertion candidates",
            "",
            "Clauses below contain lexical evidence for more than one applicability subtype. "
            "They are candidates for future multi-label/domain-model analysis.",
            "",
        ]
    )
    if not multi:
        lines.append("No candidates detected.")
    else:
        for item in multi:
            labels = ", ".join(f"`{label}`" for label in item["detected_subtypes"])
            lines.append(
                f"- `{item['document_key']}:{item['reference'] or item['clause_id']}`: {labels}"
            )
    return "\n".join(lines).rstrip() + "\n"


def _applicability_vote_label(clause: ClauseConsensus, vote: Any) -> str:
    if not vote.applicability_present or vote.applicability_function is None:
        return _NONE
    return vote.applicability_function.value


def _has_applicability_disagreement(clause: ClauseConsensus) -> bool:
    return len({_applicability_vote_label(clause, vote) for vote in clause.votes}) > 1


def _applicability_conflict_diagnostics(
    clauses: tuple[ClauseConsensus, ...],
) -> dict[str, Any]:
    clusters: Counter[str] = Counter()
    presence_disagreement = 0
    subtype_disagreement = 0
    clause_count = 0
    for clause in clauses:
        labels = [_applicability_vote_label(clause, vote) for vote in clause.votes]
        if len(set(labels)) <= 1:
            continue
        clause_count += 1
        present_values = {label != _NONE for label in labels}
        if len(present_values) > 1:
            presence_disagreement += 1
        present_labels = {label for label in labels if label != _NONE}
        if len(present_labels) > 1:
            subtype_disagreement += 1
        counts = Counter(labels)
        signature = " ↔ ".join(
            f"{label} ({counts[label]})" for label in sorted(counts, key=_applicability_sort_key)
        )
        clusters[signature] += 1
    return {
        "clause_count": clause_count,
        "presence_disagreement_count": presence_disagreement,
        "subtype_disagreement_count": subtype_disagreement,
        "clusters": [
            {"signature": signature, "count": count} for signature, count in clusters.most_common()
        ],
    }


def _applicability_sort_key(label: str) -> tuple[int, str]:
    order = {
        "applicability_condition": 0,
        "inclusion": 1,
        "exclusion": 2,
        "exception": 3,
        _NONE: 4,
    }
    return order.get(label, 5), label


def _applicability_model_fitness(clauses: tuple[ClauseConsensus, ...]) -> list[dict[str, Any]]:
    stats: dict[str, Counter[str]] = defaultdict(Counter)
    reference_presence: dict[str, list[bool]] = defaultdict(list)
    reference_subtype: dict[str, list[bool]] = defaultdict(list)

    for clause in clauses:
        conflict = _has_applicability_disagreement(clause)
        is_reference = clause.applicability_category in {
            ConsensusCategory.UNANIMOUS,
            ConsensusCategory.STRONG,
        }
        accepted_subtype = (
            clause.proposed_applicability_functions[0].value
            if clause.applicability_present and clause.proposed_applicability_functions
            else None
        )
        for vote in clause.votes:
            item = stats[vote.model_id]
            item["vote_count"] += 1
            if vote.applicability_present:
                item["present_count"] += 1
            else:
                item["none_count"] += 1
            if conflict:
                item["conflict_vote_count"] += 1
                if not vote.applicability_present:
                    item["conflict_none_count"] += 1
            if is_reference:
                reference_presence[vote.model_id].append(
                    vote.applicability_present == clause.applicability_present
                )
                if clause.applicability_present and accepted_subtype is not None:
                    reference_subtype[vote.model_id].append(
                        vote.applicability_present
                        and vote.applicability_function is not None
                        and vote.applicability_function.value == accepted_subtype
                    )

    result = []
    for model_id in sorted(stats):
        item = stats[model_id]
        vote_count = item["vote_count"]
        conflict_votes = item["conflict_vote_count"]
        result.append(
            {
                "model_id": model_id,
                "vote_count": vote_count,
                "present_count": item["present_count"],
                "none_count": item["none_count"],
                "none_rate": item["none_count"] / vote_count if vote_count else 0.0,
                "conflict_vote_count": conflict_votes,
                "conflict_none_count": item["conflict_none_count"],
                "conflict_none_rate": (
                    item["conflict_none_count"] / conflict_votes if conflict_votes else 0.0
                ),
                "presence_reference_agreement_rate": _mean_bool(reference_presence[model_id]),
                "subtype_reference_agreement_rate": _mean_bool(reference_subtype[model_id]),
            }
        )
    return result


def _mean_bool(values: list[bool]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _duplicate_diagnostics(clauses: tuple[ClauseConsensus, ...]) -> dict[str, Any]:
    review = [clause for clause in clauses if clause.requires_review and clause.clause_text]
    exact_groups: dict[str, list[ClauseConsensus]] = defaultdict(list)
    for clause in review:
        exact_groups[_normalize_text(clause.clause_text or "")].append(clause)
    exact = [group for group in exact_groups.values() if len(group) > 1]

    assigned = {clause.clause_id for group in exact for clause in group}
    near_pairs: list[tuple[ClauseConsensus, ClauseConsensus]] = []
    candidates = [clause for clause in review if clause.clause_id not in assigned]
    for index, left in enumerate(candidates):
        left_text = _normalize_text(left.clause_text or "")
        if len(left_text) < 40:
            continue
        for right in candidates[index + 1 :]:
            right_text = _normalize_text(right.clause_text or "")
            if not _lengths_are_comparable(left_text, right_text):
                continue
            ratio = SequenceMatcher(None, left_text, right_text, autojunk=False).ratio()
            if ratio >= _NEAR_DUPLICATE_THRESHOLD:
                near_pairs.append((left, right))

    near_groups = _connected_groups(near_pairs)
    clusters = [
        _duplicate_cluster_payload("exact", group)
        for group in sorted(exact, key=lambda value: (-len(value), value[0].clause_id))
    ]
    clusters.extend(
        _duplicate_cluster_payload("near", group)
        for group in sorted(near_groups, key=lambda value: (-len(value), value[0].clause_id))
    )
    return {
        "review_clause_count": len(review),
        "exact_cluster_count": len(exact),
        "near_cluster_count": len(near_groups),
        "clusters": clusters,
    }


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _lengths_are_comparable(left: str, right: str) -> bool:
    longest = max(len(left), len(right))
    return longest > 0 and min(len(left), len(right)) / longest >= 0.85


def _connected_groups(
    pairs: list[tuple[ClauseConsensus, ClauseConsensus]],
) -> list[list[ClauseConsensus]]:
    objects: dict[str, ClauseConsensus] = {}
    edges: dict[str, set[str]] = defaultdict(set)
    for left, right in pairs:
        objects[left.clause_id] = left
        objects[right.clause_id] = right
        edges[left.clause_id].add(right.clause_id)
        edges[right.clause_id].add(left.clause_id)
    groups: list[list[ClauseConsensus]] = []
    seen: set[str] = set()
    for clause_id in sorted(objects):
        if clause_id in seen:
            continue
        stack = [clause_id]
        component: list[ClauseConsensus] = []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(objects[current])
            stack.extend(edges[current] - seen)
        if len(component) > 1:
            groups.append(sorted(component, key=lambda clause: clause.clause_id))
    return groups


def _duplicate_cluster_payload(kind: str, group: list[ClauseConsensus]) -> dict[str, Any]:
    return {
        "kind": kind,
        "size": len(group),
        "clause_ids": [clause.clause_id for clause in group],
        "references": [
            f"{clause.document_key}:{clause.reference or clause.clause_id}" for clause in group
        ],
    }


def _multi_assertion_candidates(clauses: tuple[ClauseConsensus, ...]) -> list[dict[str, Any]]:
    result = []
    for clause in clauses:
        subtypes = _detect_applicability_subtypes(clause.clause_text or "")
        if len(subtypes) <= 1:
            continue
        result.append(
            {
                "clause_id": clause.clause_id,
                "document_key": clause.document_key,
                "reference": clause.reference,
                "detected_subtypes": sorted(subtypes, key=_applicability_sort_key),
                "requires_review": clause.requires_review,
            }
        )
    return result


def _detect_applicability_subtypes(text: str) -> set[str]:
    detected: set[str] = set()
    statements = re.split(r"(?<=[.!?;])\s+|\n+", text.casefold())
    for statement in statements:
        if re.search(r"\b(except|exception|unless)\b", statement):
            detected.add("exception")
        if re.search(
            r"\b(does not apply|do not apply|not applicable|excluded|excludes|outside the scope)\b",
            statement,
        ):
            detected.add("exclusion")
        inclusion = bool(
            re.search(r"\b(applies to|applicable to|includes|within the scope|covers)\b", statement)
        )
        condition = bool(
            re.search(r"\b(if|when|where|provided that|subject to|only if)\b", statement)
        )
        if inclusion and condition:
            detected.add("applicability_condition")
        elif inclusion:
            detected.add("inclusion")
    return detected


def _stage_contributions(cascade_stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "stage_id": stage["stage_id"],
            "entered_clause_count": stage["entered_clause_count"],
            "unresolved_clause_count": stage["unresolved_clause_count"],
            "newly_resolved_counts": dict(stage["newly_resolved_counts"]),
        }
        for stage in cascade_stages
    ]


def _format_optional_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"
