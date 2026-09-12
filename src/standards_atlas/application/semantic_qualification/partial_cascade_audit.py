"""Immutable cause analysis of a complete stored partial cascade or its archive."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from standards_atlas.application.semantic_qualification.acceptance_profiles import profile_from_plan
from standards_atlas.application.semantic_qualification.cascade_diagnostics import (
    describe_mixed_consensus,
    describe_model_run,
)
from standards_atlas.application.semantic_qualification.cascade_replay_source import (
    CascadeReplaySource,
)
from standards_atlas.application.semantic_qualification.mixed_evidence import MixedConsensusReport
from standards_atlas.application.semantic_qualification.partial_cascade import (
    DEFAULT_CASCADE_PROMPT,
    effective_cascade_configuration,
)
from standards_atlas.application.semantic_qualification.partial_cascade_archive import (
    verify_partial_cascade,
)
from standards_atlas.application.semantic_qualification.performance import RequestTiming


def audit_partial_cascade(
    *,
    experiment: Path,
    output_directory: Path,
    resources: Path,
) -> dict[str, Any]:
    """Re-use archive replay validation; diagnostics are never adoption authority.

    Full source/requests/observations are required. A stand-alone summary cannot
    explain model failures and is deliberately rejected rather than embellished.
    """
    source_path, output = experiment.resolve(), output_directory.resolve()
    if (
        output.exists()
        or output == source_path
        or (source_path.is_dir() and output.is_relative_to(source_path))
    ):
        raise ValueError("audit output must be a new directory separate from the experiment")
    for protected in (
        "data",
        "src/standards_atlas/resources",
        ".atlas/data/documents",
        ".atlas/data/knowledge-evidence",
    ):
        if output.is_relative_to(Path(protected).resolve()):
            raise ValueError("audit output must be separate from canonical/public resources")
    if source_path.is_file() and source_path.suffix.lower() != ".zip":
        raise ValueError("cascade audit needs the experiment directory or ZIP, not only a summary")
    source = CascadeReplaySource(source_path)
    try:
        marker = source.locate("partial-cascade-plan.json", suffix="/partial-cascade-plan.json")
        if marker is None:
            raise ValueError("missing partial-cascade-plan.json; supply the complete experiment")
        prefix = marker.removesuffix("partial-cascade-plan.json")
        names = {n.removeprefix(prefix) for n in source.names if n.startswith(prefix)}
        if any(name.endswith(".partial-run.lock") for name in names):
            raise ValueError("cascade has an active writer; audit a closed run or immutable copy")

        def read(name):
            return source.read(prefix + name)

        required = {
            "partial-cascade-inputs.json",
            "partial-cascade-resources.json",
            "partial-cascade-report.json",
            "mixed-consensus-report.json",
        }
        if required - names:
            raise ValueError("missing cascade artifacts: " + ", ".join(sorted(required - names)))
        final, _, manifest = verify_partial_cascade(read=read, names=names, resources=resources)
        plan = json.loads(read("partial-cascade-plan.json"))
        summary = json.loads(read("partial-cascade-report.json"))
        stages, active_prefixes = [], []
        active_timing = RequestTiming()
        for stage in summary["stages"]:
            mixed = MixedConsensusReport.model_validate_json(read(stage["report"]))
            models = []
            for item in stage["models"]:
                active_prefixes.append(item["prefix"])
                model = describe_model_run(
                    prefix=item["prefix"],
                    model_id=item["model_id"],
                    read=read,
                    names=names,
                )
                active_timing = active_timing.plus(
                    RequestTiming.model_validate(model["request_timing_all_executions_in_revision"])
                )
                models.append(model)
            focused_models = []
            for item in stage.get("focused_resolution", {}).get("jobs", []):
                active_prefixes.append(item["prefix"])
                model = describe_model_run(
                    prefix=item["prefix"],
                    model_id=item["model_id"],
                    read=read,
                    names=names,
                )
                model["same_voter_refinement"] = True
                active_timing = active_timing.plus(
                    RequestTiming.model_validate(model["request_timing_all_executions_in_revision"])
                )
                focused_models.append(model)
            stages.append(
                {
                    "stage_id": stage["stage_id"],
                    "entered": stage["entered"],
                    "newly_completed": stage["newly_completed"],
                    "cumulative": describe_mixed_consensus(mixed),
                    "entered_cases": describe_mixed_consensus(
                        mixed,
                        example_ids=set(stage["selected_example_ids"]),
                        include_cases=True,
                    ),
                    "models": models,
                }
            )
            if "focused_resolution" in stage:
                stages[-1]["focused_models"] = focused_models
        retired, detail = RequestTiming(), RequestTiming()
        for name in sorted(names):
            if not name.endswith("/request-timing.json") or "/executions/execution-" not in name:
                continue
            if name.startswith("stages/") and not any(
                name.startswith(p + "/") for p in active_prefixes
            ):
                retired = retired.plus(RequestTiming.model_validate_json(read(name)))
            elif name.startswith(("policy/", "policy-history/")):
                detail = detail.plus(RequestTiming.model_validate_json(read(name)))
        all_timing = active_timing.plus(retired)
        models = [m for s in stages for m in (*s["models"], *s.get("focused_models", []))]
        policy_names = sorted(
            n
            for n in names
            if n.startswith("policy/") and n.endswith("applicability-policy-run.json")
        )
        result = {
            "schema_version": "1.0",
            "kind": "partial-cascade-audit",
            "diagnostic_only": True,
            "acceptance_changed": False,
            "gateway_request_count": 0,
            "source_execution_requested": summary["executed"],
            "source_run_mode": "executed" if summary["executed"] else "planned",
            "source_evidence_verified": True,
            "selected_count": len(final.clauses),
            "effective_configuration": effective_cascade_configuration(
                manifest,
                resources,
                plan.get("prompt_version", DEFAULT_CASCADE_PROMPT),
                profile_from_plan(plan),
                plan.get("stage_limit"),
            ),
            "final": describe_mixed_consensus(final, include_cases=True),
            "stages": stages,
            "physical_work": {
                "active_revisions": active_timing.model_dump(mode="json"),
                "retired_revisions": retired.model_dump(mode="json"),
                "cascade_total": all_timing.model_dump(mode="json"),
                "applicability_detail": detail.model_dump(mode="json"),
                "nominal_stage_model_clause_combinations": sum(
                    len(s["requested_example_ids"]) * len(s["models"]) for s in summary["stages"]
                ),
                "focused_planned_model_clause_combinations": sum(
                    len(s.get("focused_resolution", {}).get("jobs", [])) for s in summary["stages"]
                ),
                "planned_nonempty_requests": sum(
                    m["plan_summary"]["plan_count"]
                    - m["plan_summary"]["clauses_with_no_model_questions"]
                    for m in models
                ),
                "active_cases_with_recorded_attempts": sum(
                    m["cases_with_recorded_attempts"] for m in models
                ),
                "active_additional_attempts_within_executions": sum(
                    m["additional_attempts_within_executions"] for m in models
                ),
                "active_repeated_case_executions": sum(
                    m["repeated_case_executions"] for m in models
                ),
                "attempt_counts_reconciled": all(m["attempt_timing_count_matches"] for m in models),
                "gateway_errors_reconciled": all(m["gateway_error_count_matches"] for m in models),
                "source_summary_timing_matches": (
                    all_timing.request_count
                    == summary["cascade_request_timing_all_executions"]["request_count"]
                    and all_timing.failed_request_count
                    == summary["cascade_request_timing_all_executions"]["failed_request_count"]
                ),
            },
            "applicability": {
                "gate_is_final_policy": False,
                "policy_artifacts_present": policy_names,
                "policy_semantics_verified": False,
                "note": "Gate diagnostics are not final policy or Golden FP/FN evaluation.",
            },
            "limitations": [
                "No new inference, no changed thresholds, no semantic accuracy claim.",
                "Retired revisions count as work, never as extra voters.",
                "Stored hashes bind evidence, not runtime model attestation.",
            ],
        }
        # Detect concurrent mutation even without a cooperating writer lock.
        fingerprints = dict(source.fingerprints)
        for name, expected in fingerprints.items():
            if hashlib.sha256(source.read(name)).hexdigest() != expected:
                raise ValueError("cascade artifact changed during audit")
        result["artifact_fingerprints"] = fingerprints
    finally:
        source.close()
    output.mkdir(parents=True)
    (output / "partial-cascade-audit.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Partial cascade audit",
        "",
        "Read-only; no new inference or acceptance changes.",
        f"Prompt: `{result['effective_configuration']['prompt_version']}`",
        "",
        "| Stage | Entered | Newly completed | Open required attributes |",
        "|---|---:|---:|---|",
    ]
    for stage in result["stages"]:
        blocked = stage["entered_cases"]["open_required_attribute_counts"]
        lines.append(
            f"| {stage['stage_id']} | {stage['entered']} | {stage['newly_completed']} | "
            + ", ".join(f"{k}: {v}" for k, v in blocked.items())
            + " |"
        )
    lines += [
        "",
        "Detailed cases, empty/null values, provenance, model failures and attempt "
        "reconciliation are in partial-cascade-audit.json.",
        "",
    ]
    (output / "partial-cascade-audit.md").write_text("\n".join(lines), encoding="utf-8")
    return result
