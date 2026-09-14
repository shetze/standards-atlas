"""Qualification gates from replay-verified repetitions, never summary assertions."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.schema import require_current_payload
from standards_atlas.application.semantic_qualification.applicability_policy_evaluation import (
    evaluate_applicability_policy,
)
from standards_atlas.application.semantic_qualification.campaign_execution import (
    FRESH_MODES,
    job_key,
    verify_job,
)
from standards_atlas.application.semantic_qualification.campaign_selection import load_campaign
from standards_atlas.application.semantic_qualification.cascade_diagnostics import (
    describe_mixed_consensus,
    describe_model_run,
)
from standards_atlas.application.semantic_qualification.mixed_evidence import MixedConsensusReport
from standards_atlas.application.semantic_qualification.partial_proposals import _atomic_json
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    SemanticPredicate,
    predicate_passes,
)


def semantic_results(mixed, suites, sentinels):
    """Accepted per-attribute evidence only; abstentions do not disappear from recall."""
    by_id = {c.example_id: c for c in mixed.clauses}
    results = []
    for suite in suites:
        cases = []
        for check in suite.cases:
            clause = by_id.get(check.example_id)
            for attribute, predicate in check.attributes.items():
                decision = clause.decision(attribute) if clause else None
                status = (
                    "unavailable"
                    if decision is None or not decision.known
                    else "passed"
                    if predicate_passes(decision.value, predicate)
                    else "failed"
                )
                cases.append(
                    {
                        "example_id": check.example_id,
                        "attribute": attribute,
                        "status": status,
                        "actual": decision.value if decision else None,
                        "expected": predicate.model_dump(exclude_unset=True),
                    }
                )
        results.append(
            {
                "suite_id": suite.id,
                "split": suite.split,
                "reviewed": suite.status == "published",
                "cases": cases,
                "status_counts": dict(Counter(c["status"] for c in cases)),
            }
        )
    # Engineering sentinels are regression guards, never substituted for reviewed holdout gold.
    for suite in sentinels:
        cases = []
        for check in suite["cases"]:
            clause = by_id.get(check["example_id"])
            predicates = dict(check.get("attribute_checks", {}))
            if "process_check" in check:
                predicates["process_functions"] = check["process_check"]
            for attribute, raw in predicates.items():
                predicate = SemanticPredicate.model_validate(raw)
                decision = clause.decision(attribute) if clause else None
                status = (
                    "unavailable"
                    if decision is None or not decision.known
                    else "passed"
                    if predicate_passes(decision.value, predicate)
                    else "failed"
                )
                cases.append(
                    {
                        "example_id": check["example_id"],
                        "attribute": attribute,
                        "status": status,
                        "actual": decision.value if decision else None,
                        "expected": raw,
                    }
                )
            if "expected_primary_state" in check:
                decision = clause.decision_plan.decision("primary_function") if clause else None
                matches = decision is not None and decision.state == check["expected_primary_state"]
                if "expected_primary_value" in check:
                    matches = matches and decision.value == check["expected_primary_value"]
                cases.append(
                    {
                        "example_id": check["example_id"],
                        "attribute": "source_primary",
                        "status": "passed" if matches else "failed",
                    }
                )
        results.append(
            {
                "suite_id": suite["id"],
                "split": "sentinels",
                "reviewed": False,
                "cases": cases,
                "status_counts": dict(Counter(c["status"] for c in cases)),
            }
        )
    return results


def _semantic_gate(results, spec):
    covered = {"development": set(), "holdout": set()}
    errors, unavailable = Counter(), Counter()
    for result in results:
        for case in result["cases"]:
            if result["reviewed"]:
                covered[result["split"]].add(case["attribute"])
            if case["status"] == "failed":
                errors[case["attribute"]] += 1
            if case["status"] == "unavailable":
                unavailable[case["attribute"]] += 1
    missing = {
        split: sorted(set(spec.required_semantic_attributes) - attrs)
        for split, attrs in covered.items()
    }
    return {
        "passed": not any(missing.values())
        and sum(errors.values()) <= spec.max_semantic_errors
        and sum(unavailable.values()) <= spec.max_semantic_unavailable,
        "missing_reviewed_dimensions": missing,
        "errors_by_attribute": dict(errors),
        "unavailable_by_attribute": dict(unavailable),
        "max_errors": spec.max_semantic_errors,
        "max_unavailable": spec.max_semantic_unavailable,
    }


def _cohort_metrics(mixed, ids):
    clauses = [c for c in mixed.clauses if c.example_id in set(ids)]
    n = len(ids)
    completed = [c for c in clauses if c.completed]
    sources = Counter()
    for clause in completed:
        origins = {clause.decision(a).source for a in mixed.completion_profile.required_attributes}
        sources["mixed" if len(origins) > 1 else next(iter(origins))] += 1
    return {
        "selected": n,
        "accounted": len(clauses),
        "completed": len(completed),
        "completion_rate": len(completed) / n if n else None,
        "completion_sources": dict(sources),
        "unresolved": n - len(completed),
    }


def _run_details(verified, *, root, selection, suites, sentinels):
    mixed = verified["mixed"]
    summary_path = root / "run/partial-cascade-report.json"
    stages, first = [], None
    names = {
        p.relative_to(root / "run").as_posix() for p in (root / "run").rglob("*") if p.is_file()
    }

    def read(name):
        return (root / "run" / name).read_bytes()

    if summary_path.is_file():
        summary = json.loads(summary_path.read_bytes())
        for stage in summary["stages"]:
            report = MixedConsensusReport.model_validate_json(read(stage["report"]))
            first = first or report
            models = [
                describe_model_run(
                    prefix=m["prefix"], model_id=m["model_id"], read=read, names=names
                )
                for m in stage["models"]
            ]
            focused = [
                describe_model_run(
                    prefix=m["prefix"], model_id=m["model_id"], read=read, names=names
                )
                for m in stage.get("focused_resolution", {}).get("jobs", [])
            ]
            stages.append(
                {
                    "stage": stage["stage_id"],
                    "entered": stage["entered"],
                    "newly_completed": stage["newly_completed"],
                    "cohorts": {
                        name: _cohort_metrics(report, ids)
                        for name, ids in selection["cohorts"].items()
                    },
                    "diagnostics": describe_mixed_consensus(report),
                    "models": models,
                    "focused_same_voter_jobs": focused,
                }
            )
    semantics = semantic_results(mixed, suites, sentinels)
    efficient = _cohort_metrics(first, selection["cohorts"]["representative"]) if first else None
    final = {name: _cohort_metrics(mixed, ids) for name, ids in selection["cohorts"].items()}
    return {
        "stages": stages,
        "final_cohorts": final,
        "efficient_representative": efficient,
        "semantic_results": semantics,
        "full_population": _cohort_metrics(mixed, [c.example_id for c in mixed.clauses]),
        "efficient_population": (
            _cohort_metrics(first, [c.example_id for c in mixed.clauses]) if first else None
        ),
    }


def golden_coverage_eligible(golden, evaluation, minimum):
    """Require the full published reference population and both binary classes."""
    return (
        evaluation.published_cases >= minimum
        and any(c.expected.present for c in golden.cases if c.status == "published")
        and any(not c.expected.present for c in golden.cases if c.status == "published")
    )


def evaluate_campaign(*, campaign: Path, resources: Path, write: bool = True):
    campaign = campaign.resolve()
    if (campaign / ".partial-run.lock").exists():
        raise ValueError("cannot qualify a campaign with an active writer")
    loaded = load_campaign(campaign, resources)
    definition, spec, _population, golden, suites, sentinels, selection = loaded
    rows, bindings, event_owners = [], set(), {}
    snapshots = {}
    expected = [
        (v, mode, rep)
        for v in spec.variants
        for mode in FRESH_MODES
        for rep in range(1, spec.repetitions + 1)
    ]
    candidate_variant = next(v for v in spec.variants if v.id == spec.candidate)
    expected.append((candidate_variant, "full_baseline", 1))
    for variant, mode, rep in expected:
        key = job_key(variant.id, mode, rep)
        root = campaign / key
        row = {
            "job": key,
            "variant": variant.id,
            "mode": mode,
            "repetition": rep,
            "status": "missing",
            "qualifies": False,
        }
        rows.append(row)
        if not (root / "repeat.json").is_file():
            continue
        try:
            verified = verify_job(campaign=campaign, key=key, resources=resources, loaded=loaded)
            receipt = verified["receipt"]
            binding = receipt["binding"]["run_id"]
            if binding in bindings:
                raise ValueError("duplicate independent repetition run identity")
            bindings.add(binding)
            for event in verified["events"]:
                if event["event_id"] in event_owners:
                    raise ValueError("physical request counted in multiple repetitions")
                event_owners[event["event_id"]] = key
            snapshots[key + "/repeat.json"] = verified["artifact_sha256"]
            details = _run_details(
                verified, root=root, selection=selection, suites=suites, sentinels=sentinels
            )
            policy = verified["matrix"].applicability_decision_policy
            golden_result = evaluate_applicability_policy(
                golden,
                verified["policy"],
                max_false_positive=min(2, policy.max_false_positive),
                max_false_negative=min(2, policy.max_false_negative),
            )
            semantics = _semantic_gate(details["semantic_results"], spec)
            synthetic = any(
                (f.authority or "").startswith("fixture:")
                for c in verified["mixed"].clauses
                for f in c.decision_plan.source.facts
            )
            # A fixed-detail pass must actually exercise details, not repeat empty work.
            detail_exercised = any(
                e["request"]["task"] != "semantic-attribute-observation" for e in verified["events"]
            )
            complete_gold = golden_coverage_eligible(
                golden, golden_result, spec.minimum_published_golden_cases
            )
            qualifies = (
                golden_result.passed
                and complete_gold
                and not synthetic
                and detail_exercised
                and (mode == "fresh_detail_fixed_presence" or semantics["passed"])
            )
            row.update(
                status="verified",
                qualifies=qualifies,
                evidence_sha256=verified["artifact_sha256"],
                freshness_verified=True,
                synthetic_sources=synthetic,
                final_applicability=golden_result.model_dump(mode="json"),
                golden_coverage_eligible=complete_gold,
                detail_exercised=detail_exercised,
                semantic_gate=semantics,
                diagnostics=details,
                physical_work=verified["timing"].model_dump(mode="json"),
                tokens=verified["usage"],
                recorded_wall_seconds_last_invocation=receipt["wall_seconds_last_invocation"],
                wall_time_note="last invocation only; request wall sums are reported separately",
            )
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            row.update(status="invalid_evidence", error=str(exc))
    # Comparisons report complete independent repeats, not concatenated votes or cherry-picked best.
    baseline = [
        r for r in rows if r["variant"] == spec.baseline and r["mode"] == "fresh_end_to_end"
    ]
    candidate = [
        r for r in rows if r["variant"] == spec.candidate and r["mode"] == "fresh_end_to_end"
    ]
    baseline_verified = all(r["status"] == "verified" for r in baseline)
    candidate_verified = all(r["status"] == "verified" for r in candidate)
    cost = {
        "comparable": baseline_verified and candidate_verified,
        "request_ratio": None,
        "max_request_ratio": spec.max_request_ratio,
        "passed": False,
        "scope": "pooled physical cascade+focus+detail calls across same selected repetitions",
    }
    comparisons = []
    if cost["comparable"]:
        b = sum(r["physical_work"]["request_count"] for r in baseline)
        c = sum(r["physical_work"]["request_count"] for r in candidate)
        ratio = c / b if b else 1.0 if not c else None
        cost.update(
            baseline_requests=b,
            candidate_requests=c,
            request_ratio=ratio,
            passed=ratio is not None and ratio <= spec.max_request_ratio,
        )
        for left, right in zip(baseline, candidate, strict=True):
            a = left["diagnostics"]["efficient_representative"]
            b = right["diagnostics"]["efficient_representative"]
            comparisons.append(
                {
                    "repetition": left["repetition"],
                    "baseline": a,
                    "candidate": b,
                    "completion_rate_delta": b["completion_rate"] - a["completion_rate"],
                }
            )
    candidate_repeats = [
        r for r in rows if r["variant"] == spec.candidate and r["mode"] in FRESH_MODES
    ]
    full = rows[-1]
    pre_full = (
        baseline_verified and all(r["qualifies"] for r in candidate_repeats) and cost["passed"]
    )
    eligible = pre_full and full["status"] == "verified" and full["qualifies"]
    reasons = []
    if not baseline_verified:
        reasons.append("baseline_repetitions_missing_or_unverified")
    if not all(r["qualifies"] for r in candidate_repeats):
        reasons.append("candidate_fresh_quality_repetitions_incomplete_or_failed")
    if not cost["passed"]:
        reasons.append("physical_request_budget_not_demonstrated")
    if full["status"] != "verified" or not full["qualifies"]:
        reasons.append("qualified_full_baseline_missing_or_failed")
    target_observed = (
        full["diagnostics"]["efficient_population"]["completion_rate"]
        if full["status"] == "verified"
        else None
    )
    result = {
        "schema_version": "1.0",
        "kind": "partial-qualification-evaluation",
        "campaign_sha256": definition["campaign_sha256"],
        "candidate": spec.candidate,
        "baseline": spec.baseline,
        "selection": selection,
        "evidence": snapshots,
        "repetitions": rows,
        "cost_comparison": cost,
        "paired_comparison": comparisons,
        "pre_full_eligible": pre_full,
        "activation_eligible": eligible,
        "blocking_reasons": reasons,
        "efficient_target": spec.efficient_target,
        "full_population_efficient_rate": target_observed,
        "efficient_target_observed": (
            target_observed >= spec.efficient_target if target_observed is not None else None
        ),
        "target_note": (
            "80% is separate from semantic eligibility; useful profiles below it "
            "are not target successes"
        ),
        "efficient_target_qualified": bool(
            eligible and target_observed is not None and target_observed >= spec.efficient_target
        ),
        "model_calls": 0,
        "default_workflow_changed": False,
        "scope": (
            "partial B3/B4 candidates; earlier full-output B0/B1/B2 artifacts "
            "remain separate controls"
        ),
        "limits": [
            "review provenance is supplied, not independently certified by this tool",
            "fresh events prove recorded calls, not runtime model artifact attestation",
            "a frozen sample is not a statistical guarantee for all future clauses",
            "full baseline is accounted even when individual clauses remain unresolved",
        ],
    }
    require_current_payload("partial-qualification-evaluation", result)
    result["evaluation_sha256"] = structure_fingerprint(result)
    if write:
        output = campaign / "evaluations" / result["evaluation_sha256"]
        target = output / "qualification-evaluation.json"
        if target.exists():
            if json.loads(target.read_bytes()) != result:
                raise ValueError("immutable evaluation content changed")
        else:
            _atomic_json(target, result)
            lines = [
                "# Partial-cascade qualification",
                "",
                f"Campaign: `{definition['campaign_sha256']}`",
                "",
                f"Ready for full baseline: **{pre_full}**; activation eligible: **{eligible}**.",
                f"Full-population Efficient rate: **{target_observed}** "
                f"(target {spec.efficient_target}).",
                "",
                "| Variant | Mode | Repeat | Evidence | Qualifies |",
                "|---|---|---:|---|---|",
            ]
            lines += [
                f"| {r['variant']} | {r['mode']} | {r['repetition']} | "
                f"{r['status']} | {r['qualifies']} |"
                for r in rows
            ]
            lines += [
                "",
                "## Blocking reasons",
                "",
                *[f"- {reason}" for reason in reasons],
                "",
                "Golden, representative and declared holdout cohorts are separate in the JSON.",
                "No values, acceptance rules or source authority were changed by evaluation.",
            ]
            (output / "qualification-evaluation.md").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
    return result
