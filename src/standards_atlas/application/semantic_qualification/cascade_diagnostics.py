"""Read-only explanations of partial cascade acceptance and recorded model work.

No changed votes or inferred missing outcomes. Cumulative state, entered clauses,
logical observations and physical attempts have deliberately separate denominators.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from itertools import combinations
from pathlib import Path
from typing import Any

from standards_atlas.application.semantic_qualification.mixed_evidence import MixedConsensusReport
from standards_atlas.application.semantic_qualification.partial_diagnostics import (
    summarize_partial_plans,
)
from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_ATTRIBUTES,
    PartialObservation,
    PartialRequestPlan,
    partial_response_diagnostics,
)
from standards_atlas.application.semantic_qualification.performance import RequestTiming


def value_shape(value: Any) -> str:
    """Null, negative and empty sets are observed values, not missing observations."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | tuple):
        return "nonempty_set" if value else "empty_set"
    return "scalar"


def _counts(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def presentation_metrics(report: MixedConsensusReport, *, execute: bool) -> dict[str, Any]:
    """Keep consensus fingerprints stable; an unexecuted plan is not a measured 0%."""
    metrics = report.metrics.copy()
    metrics["completion_profile_eligible"] = report.completion_profile.benchmark_eligible
    synthetic = any(
        (f.authority or "").startswith("fixture:")
        for c in report.clauses
        for f in c.decision_plan.source.facts
    )
    metrics["benchmark_eligible"] = bool(
        execute and metrics["completion_profile_eligible"] and not synthetic
    )
    metrics["synthetic_fixture_sources"] = synthetic
    metrics["completion_rate"] = report.metrics["completion_rate"] if execute else None
    metrics["measurement_status"] = "observed_not_qualified" if execute else "not_executed"
    return metrics


def describe_mixed_consensus(
    report: MixedConsensusReport,
    *,
    example_ids: set[str] | None = None,
    include_cases: bool = False,
) -> dict[str, Any]:
    """Explain the same decisions used for routing; never invent an alternate threshold."""
    clauses = [c for c in report.clauses if example_ids is None or c.example_id in example_ids]
    required = report.completion_profile.required_attributes
    blocks = {c.example_id: tuple(k for k in required if not c.decision(k).known) for c in clauses}
    cases = []
    if include_cases:
        for clause in clauses:
            cases.append(
                {
                    "example_id": clause.example_id,
                    "document_key": clause.document_key,
                    "reference": clause.reference,
                    "completed": clause.completed,
                    "open_required_attributes": list(blocks[clause.example_id]),
                    "escalation_reasons": list(clause.escalation_reasons),
                    "consistency_reasons": list(clause.consistency_reasons),
                    "source_origin": clause.decision_plan.source.origin,
                    "attributes": {
                        d.attribute: {
                            "status": d.status,
                            "value": d.value,
                            "value_shape": value_shape(d.value) if d.known else "not_accepted",
                            "proposed_value": d.proposed_value,
                            "source": d.source,
                            "accepting_stage": d.stage,
                            "rule": d.rule,
                            "observed_model_count": d.observed_model_count,
                            "supporting_models": list(d.supporting_models),
                            "model_values": d.model_values,
                            "reasons": list(d.reasons),
                            "diagnostics": list(d.diagnostics),
                        }
                        for d in clause.decisions
                    },
                }
            )
    result = {
        "clause_count": len(clauses),
        "completed_clause_count": sum(c.completed for c in clauses),
        "required_attributes": list(required),
        "open_required_attribute_counts": {
            k: sum(k in blocked for blocked in blocks.values()) for k in required
        },
        "exclusive_blocker_counts": {
            k: sum(blocks[c.example_id] == (k,) and not c.consistency_reasons for c in clauses)
            for k in required
        },
        "blocker_combinations": _counts(
            ",".join(blocks[c.example_id]) + ("|consistency" if c.consistency_reasons else "")
            for c in clauses
            if not c.completed
        ),
        "pairwise_blocker_overlap": {
            f"{left}+{right}": sum(left in b and right in b for b in blocks.values())
            for left, right in combinations(required, 2)
        },
        "escalation_reason_counts": _counts(r for c in clauses for r in c.escalation_reasons),
        "consistency_reason_counts": _counts(r for c in clauses for r in c.consistency_reasons),
        "attributes": {},
        "source_plans": {
            "source_origins": _counts(c.decision_plan.source.origin for c in clauses),
            "fixed_attribute_count": sum(
                d.state == "fixed"
                for c in clauses
                for d in c.decision_plan.decisions
                if d.attribute in PARTIAL_ATTRIBUTES
            ),
            "attribute_states": {
                k: _counts(c.decision_plan.decision(k).state for c in clauses)
                for k in PARTIAL_ATTRIBUTES
            },
            "pending_rule_evidence_counts": _counts(
                e.rule_id
                for c in clauses
                for d in c.decision_plan.decisions
                for e in d.evidence
                if e.qualification == "pending-review"
            ),
        },
        "process_given_knowledge_primary": {},
        "note": "Acceptance counts are not semantic accuracy; gate is not final applicability.",
    }
    for key in PARTIAL_ATTRIBUTES:
        decisions = [c.decision(key) for c in clauses]
        accepted = [d for d in decisions if d.known]
        result["attributes"][key] = {
            "status_counts": _counts(d.status for d in decisions),
            "accepted_value_shapes": _counts(value_shape(d.value) for d in accepted),
            "accepted_value_counts": _counts(
                json.dumps(d.value, sort_keys=True, ensure_ascii=False) for d in accepted
            ),
            "accepted_sources": _counts(d.source for d in accepted),
            "accepting_stages": _counts(d.stage for d in accepted),
            "participating_model_counts": _counts(str(d.observed_model_count) for d in decisions),
            "reason_counts": _counts(r for d in decisions for r in d.reasons),
        }
    cross = Counter()
    for clause in clauses:
        knowledge, process = (
            clause.decision("primary_knowledge_kind"),
            clause.decision("process_functions"),
        )
        if knowledge.known and process.known:
            cross[f"{knowledge.value}|{value_shape(process.value)}"] += 1
    result["process_given_knowledge_primary"] = dict(sorted(cross.items()))
    if include_cases:
        result["cases"] = cases
    return result


def classify_error(message: str) -> str:
    """Stable diagnostic families only; does not decide eligibility or retry policy."""
    text = message.lower()
    if "primary" in text and ("belong" in text or "set" in text):
        return "primary_set_contract"
    if "non-unique" in text or "uniqueitems" in text:
        return "duplicate_set_member"
    if "role" in text and ("presence" in text or "relation" in text):
        return "role_contract"
    if "identity" in text or "selector" in text or "repository" in text:
        return "response_identity"
    if "truncat" in text or "finish_reason" in text:
        return "truncation"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "schema" in text or "json" in text:
        return "schema_or_json"
    return "other"


def describe_model_run(
    *,
    prefix: str,
    model_id: str,
    root: Path | None = None,
    read: Callable[[str], bytes] | None = None,
    names: set[str] | None = None,
) -> dict[str, Any]:
    """Read a current stage revision. Retired revisions never become logical votes."""
    if read is None:
        if root is None:
            raise ValueError("model diagnostics require a root or artifact reader")
        resolved = root.resolve()

        def local_read(name):
            path = (resolved / name).resolve()
            if not path.is_relative_to(resolved):
                raise ValueError("model diagnostic path escapes cascade")
            return path.read_bytes()

        read = local_read
        names = {p.relative_to(root).as_posix() for p in (root / prefix).rglob("*") if p.is_file()}
    if names is None:
        raise ValueError("artifact names must accompany a reader")
    scoped = sorted(n for n in names if n.startswith(prefix + "/"))
    observations, plans, errors, validation_issues = [], [], [], []
    for name in scoped:
        # Only final logical artifacts, not execution copies or history.
        relative = name.removeprefix(prefix + "/")
        if len(relative.split("/")) != 3 or not relative.startswith("cases/"):
            continue
        if relative.endswith("/partial-request-plan.json"):
            plans.append(PartialRequestPlan.model_validate_json(read(name)))
        elif relative.endswith("/partial-observation.json"):
            obs = PartialObservation.model_validate_json(read(name))
            observations.append(obs)
            if obs.error:
                errors.append(obs.error)
            response_path = name.removesuffix("partial-observation.json") + "response.json"
            request_path = name.removesuffix("partial-observation.json") + "request.json"
            if response_path in names and request_path in names:
                response, request = json.loads(read(response_path)), json.loads(read(request_path))
                diagnostic = partial_response_diagnostics(
                    response.get("value"), request["output_schema"], obs.plan
                )
                validation_issues.extend(diagnostic["issues"])
    timing = RequestTiming()
    executions = {}
    attempt_errors = []
    for name in scoped:
        if "/executions/execution-" not in name:
            continue
        parent, filename = name.rsplit("/", 1)
        if filename == "request-timing.json":
            timing = timing.plus(RequestTiming.model_validate_json(read(name)))
        elif filename.startswith("attempt-") and filename.endswith(".json"):
            attempt = json.loads(read(name))
            executions.setdefault(parent, []).append(attempt)
            if attempt.get("error"):
                attempt_errors.append(attempt["error"])
    attempt_count = sum(len(v) for v in executions.values())
    executed_case_count = len({p.split("/executions/")[0] for p in executions})
    failed = [o for o in observations if o.outcome == "failed"]
    config_path = prefix + "/partial-run-plan.json"
    config = json.loads(read(config_path))["config"] if config_path in names else None
    return {
        "model_id": model_id,
        "prefix": prefix,
        "effective_configuration": config,
        "planned_clause_count": len(plans),
        "logical_observation_count": len(observations),
        "logical_status_counts": _counts(o.outcome for o in observations),
        "missing_observation_count": len(plans) - len(observations),
        "failed_with_saved_response": sum(o.response_sha256 is not None for o in failed),
        "failed_without_saved_response": sum(o.response_sha256 is None for o in failed),
        "observation_error_classes": _counts(classify_error(e) for e in errors),
        "response_issue_counts": _counts(i["code"] for i in validation_issues),
        "invalid_attribute_counts": _counts(a for i in validation_issues for a in i["attributes"]),
        "plan_summary": summarize_partial_plans(plans),
        "request_timing_all_executions_in_revision": timing.model_dump(mode="json"),
        "execution_count": len(executions),
        "cases_with_recorded_attempts": executed_case_count,
        "recorded_attempt_count": attempt_count,
        "additional_attempts_within_executions": sum(
            max(0, len(v) - 1) for v in executions.values()
        ),
        "repeated_case_executions": len(executions) - executed_case_count,
        "attempt_timing_count_matches": attempt_count == timing.request_count,
        "gateway_error_types": _counts(e.get("type", "unknown") for e in attempt_errors),
        "gateway_error_classes": _counts(
            classify_error(e.get("message", "")) for e in attempt_errors
        ),
        "recorded_gateway_error_count": len(attempt_errors),
        "gateway_error_count_matches": len(attempt_errors) == timing.failed_request_count,
        "scope": "current logical revision; all physical executions within it; not quality",
    }
