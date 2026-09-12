"""Read-only explanations of question plans; never promote hints to decisions."""

from __future__ import annotations

from collections import Counter
from typing import Any

from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_ATTRIBUTES,
    PartialRequestPlan,
)


def describe_partial_plan(plan: PartialRequestPlan) -> dict[str, Any]:
    """Explain actual source/rule gates, distinct from response and cascade quality."""
    source = plan.decision_plan
    facts = {fact.fingerprint: fact for fact in source.source.facts}
    details = {}
    for key in plan.selected_attributes:
        decision = source.decision(key)
        blockers = []
        if decision.state == "conflict":
            blockers.append("structural_conflict")
        if any(e.qualification == "pending-review" for e in decision.evidence):
            blockers.append("rule_pending_review")
        if decision.state not in {"fixed", "open"} and any(
            facts[ref].origin != "confirmed"
            for e in decision.evidence
            for ref in e.source_fingerprints
        ):
            blockers.append("source_not_confirmed")
        if decision.state == "open":
            blockers.append("no_applicable_structural_rule")
        details[key] = {
            "state": decision.state,
            "candidates": list(decision.candidates),
            "value": decision.value,
            "requested": key in plan.requested_attributes,
            "carried_acceptance": key in plan.accepted_attributes,
            "fix_blockers": blockers,
            "evidence": [e.model_dump(mode="json") for e in decision.evidence],
        }
    return {
        "source_origin": source.source.origin,
        "source_sha256": source.source_sha256,
        "rules_id": source.rules_id,
        "rules_version": source.rules_version,
        "rules_sha256": source.rules_sha256,
        "decision_plan_sha256": source.fingerprint,
        "partial_plan_sha256": plan.fingerprint,
        "source_fact_origins": dict(Counter(f.origin for f in source.source.facts)),
        "warnings": list(source.warnings),
        "selected_attribute_count": len(plan.selected_attributes),
        "requested_attribute_count": len(plan.requested_attributes),
        "fixed_attribute_count": len(plan.fixed_attributes),
        "accepted_attribute_count": len(plan.accepted_attributes),
        "attributes": details,
    }


def summarize_partial_plans(plans: list[PartialRequestPlan]) -> dict[str, Any]:
    """Count questions avoided, not accepted model responses or successful clauses."""
    descriptions = [describe_partial_plan(p) for p in plans]
    return {
        "plan_count": len(plans),
        "source_origins": dict(Counter(p.decision_plan.source.origin for p in plans)),
        "clauses_with_fixed_attributes": sum(bool(p.fixed_attributes) for p in plans),
        "fixed_attribute_count": sum(len(p.fixed_attributes) for p in plans),
        "requested_attribute_count": sum(len(p.requested_attributes) for p in plans),
        "clauses_with_no_model_questions": sum(not p.requested_attributes for p in plans),
        "attribute_states": {
            key: dict(Counter(p.decision_plan.decision(key).state for p in plans))
            for key in PARTIAL_ATTRIBUTES
        },
        "fix_blockers": dict(
            Counter(
                blocker
                for d in descriptions
                for a in d["attributes"].values()
                for blocker in a["fix_blockers"]
            )
        ),
        "production_early_exit_count": None,
        "note": (
            "Plan diagnostics only; rule qualification, source authority and acceptance unchanged."
        ),
    }
