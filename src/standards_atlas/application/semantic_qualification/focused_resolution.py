"""One budgeted first-stage refinement using the existing partial request engine.

The same provider/model identity replaces an open answer, never adds a voter.
There is no authority to override an accepted attribute or a source conflict.
A failed focused request is not automatically repeated on resume.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification.acceptance_profiles import (
    FocusedResolutionPolicy,
)
from standards_atlas.application.semantic_qualification.partial_observations import (
    ordered_attributes,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    _atomic_json,
    run_partial_proposals,
)
from standards_atlas.application.semantic_qualification.performance import RequestTiming

FOCUSED_PROMPT = "taxonomy-focused-v1"
GROUPS = {
    "primary_function": ("primary_function", "statement_functions"),
    "role_semantics_present": ("role_semantics_present", "role_relations"),
    "applicability_present": ("applicability_present",),
    "primary_knowledge_kind": ("primary_knowledge_kind", "knowledge_kinds"),
}


def focused_config(manifest, stage, model, job, policy):
    from standards_atlas.application.semantic_qualification.partial_cascade import (
        partial_config_for_model,
    )
    from standards_atlas.application.semantic_qualification.partial_requests import (
        PartialProposalConfig,
    )

    payload = partial_config_for_model(
        manifest, stage, model, prompt_version=FOCUSED_PROMPT
    ).model_dump(mode="json")
    payload.update(
        selected_attributes=job["attributes"],
        max_tokens=policy.max_output_tokens,
        retry_attempts=1,
        retry_on_truncation=False,
        truncation_retry_max_tokens=policy.max_output_tokens,
    )
    return PartialProposalConfig.model_validate(payload)


def plan_focused_resolution(*, manifest, stage, before, selected_ids, policy) -> dict[str, Any]:
    """Deterministic plan, no gold labels, forced binary choices or new models."""
    models = {m.id: m for m in manifest.models}
    candidates = []
    for clause in before.clauses:
        if clause.example_id not in selected_ids or clause.completed:
            continue
        # Source conflicts require source review, not repeated model guessing.
        if any("source_conflict" in d.reasons for d in clause.decisions):
            continue
        for priority, (attribute, group) in enumerate(GROUPS.items()):
            item = clause.decision(attribute)
            if item.known or item.status == "conflict":
                continue
            if attribute == "primary_knowledge_kind":
                offered = set(item.model_values.values()) - {None}
                if offered != {"process", "technique_or_measure"}:
                    continue
            open_count = sum(not clause.decision(a).known for a in clause.required_attributes)
            candidates.append((open_count, priority, clause.example_id, attribute, group, item))
            break  # At most one open group per clause in this bounded round.
    jobs, selected, deferred = [], set(), []
    token_cap = policy.max_total_output_tokens // policy.max_output_tokens
    capacity = min(policy.max_requests, token_cap)
    for _, _, example_id, attribute, group, item in sorted(candidates, key=lambda c: c[:3]):
        if len(selected) >= policy.max_cases or len(jobs) >= capacity:
            deferred.append({"example_id": example_id, "reason": "focused_budget_exhausted"})
            continue

        # Prefer missing evidence, then dissent. Never inspect expected labels.
        def order(model_id, item=item):
            model = models[model_id]
            voter = f"{model.provider}:{model.model_ref or model.id}"
            return (
                voter in item.model_values,
                item.model_values.get(voter) == item.proposed_value,
                stage.models.index(model_id),
            )

        voters_seen = set()
        used = 0
        for model_id in sorted(stage.models, key=order):
            model = models[model_id]
            voter = (model.provider, model.model_ref or model.id)
            if voter in voters_seen:
                continue
            voters_seen.add(voter)
            if len(jobs) >= capacity or used >= policy.models_per_case:
                break
            identity = structure_fingerprint({"example_id": example_id})
            jobs.append(
                {
                    "example_id": example_id,
                    "model_id": model_id,
                    "target_attribute": attribute,
                    "attributes": list(ordered_attributes(group)),
                    "prefix": (
                        f"stages/{stage.id}/focused/{model_id}/{identity}/run-{before.fingerprint}"
                    ),
                }
            )
            used += 1
        if used:
            selected.add(example_id)
    return {
        "schema_version": "1.0",
        "kind": "focused-resolution-plan",
        "before_consensus_sha256": before.fingerprint,
        "prompt_version": FOCUSED_PROMPT,
        "policy": policy.model_dump(mode="json"),
        "evidence_stage": stage.id + ".focused",
        "jobs": jobs,
        "deferred": deferred,
        "planned_case_count": len(selected),
        "planned_request_count": len(jobs),
        "maximum_requested_output_tokens": len(jobs) * policy.max_output_tokens,
        "new_independent_voters": 0,
        "semantic_qualification_passed": False,
    }


class _LazyFocusedGateway:
    def __init__(self, *, gateway_context, model, stack):
        self.gateway_context = gateway_context
        self.model = model
        self.stack = stack
        self.gateway = None

    def __call__(self):
        if self.gateway_context is None:
            raise ValueError("focused execution requires a model gateway")
        if self.gateway is None:
            self.gateway = self.stack.enter_context(self.gateway_context(self.model))
        return self.gateway


def _consumed(root: Path) -> tuple[int, set[str]]:
    attempts = list(root.glob("stages/*/focused/**/executions/execution-*/attempt-*.json"))
    cases = set()
    for path in attempts:
        # .../cases/<hash>/executions/execution-x/attempt-001.json
        case_root = path.parents[2]
        plan = json.loads((case_root / "partial-request-plan.json").read_bytes())
        cases.add(plan["clause"]["clause_id"])
    return len(attempts), cases


def execute_focused_resolution(
    *,
    root,
    manifest,
    stage,
    before,
    examples,
    selected_ids,
    resources,
    execute,
    gateway_context,
    progress,
    policy,
):
    from standards_atlas.application.semantic_qualification.partial_cascade import (
        read_partial_observations,
    )

    plan = plan_focused_resolution(
        manifest=manifest, stage=stage, before=before, selected_ids=selected_ids, policy=policy
    )
    by_id = {e.id: e for e in examples}
    models = {m.id: m for m in manifest.models}
    accepted = {c.example_id: c.accepted_values for c in before.clauses}
    observations, timing, job_reports = [], RequestTiming(), []
    # Pool one lazy model context for all its focused jobs.
    for model_id in stage.models:
        jobs = [job for job in plan["jobs"] if job["model_id"] == model_id]
        if not jobs:
            continue
        model = models[model_id]
        with ExitStack() as stack:
            factory = _LazyFocusedGateway(gateway_context=gateway_context, model=model, stack=stack)

            for job in jobs:
                output = root / job["prefix"]
                cfg = focused_config(manifest, stage, model, job, policy)
                used, case_ids = _consumed(root)
                item = by_id[job["example_id"]]
                clause_id = item.input["context"]["clause_id"]
                attempted = any(output.glob("cases/*/executions/execution-*/attempt-*.json"))
                permitted = (
                    not attempted
                    and used < policy.max_requests
                    and (used + 1) * policy.max_output_tokens <= policy.max_total_output_tokens
                    and (clause_id in case_ids or len(case_ids) < policy.max_cases)
                )
                payload = run_partial_proposals(
                    cfg,
                    resources=resources,
                    output_directory=output,
                    examples=(item,),
                    execute=execute and permitted,
                    gateway_factory=factory,
                    source_fingerprints={"focused-plan": structure_fingerprint(plan)},
                    accepted_decisions=accepted,
                    accepted_state_sha256=before.fingerprint,
                    progress=progress,
                )
                timing = timing.plus(RequestTiming.model_validate(payload["request_timing"]))
                names = {p.relative_to(root).as_posix() for p in output.rglob("*") if p.is_file()}
                observations.extend(
                    read_partial_observations(
                        read=lambda name: (root / name).read_bytes(),
                        names=names,
                        prefix=job["prefix"],
                        config=cfg,
                        examples=(item,),
                        resources=resources,
                        stage=plan["evidence_stage"],
                        model=model,
                        previous=before,
                    )
                )
                job_reports.append(
                    {
                        **job,
                        "execution_permitted": permitted,
                        "request_count_current_invocation": payload["request_timing"][
                            "request_count"
                        ],
                    }
                )
    path = f"stages/{stage.id}/focused-plan.json"
    _atomic_json(root / path, plan)
    return (
        tuple(observations),
        timing,
        {
            "plan": path,
            "plan_sha256": structure_fingerprint(plan),
            "before_report": f"stages/{stage.id}/mixed-before-focus-report.json",
            "jobs": job_reports,
        },
    )


def verify_focused_resolution(
    *,
    read,
    names,
    manifest,
    stage,
    before,
    examples,
    selected_ids,
    resources,
    policy,
    recorded,
):
    from standards_atlas.application.semantic_qualification.partial_cascade import (
        read_partial_observations,
    )

    plan = plan_focused_resolution(
        manifest=manifest, stage=stage, before=before, selected_ids=selected_ids, policy=policy
    )
    expected_path = f"stages/{stage.id}/focused-plan.json"
    if (
        recorded.get("plan") != expected_path
        or json.loads(read(expected_path)) != plan
        or recorded.get("plan_sha256") != structure_fingerprint(plan)
    ):
        raise ValueError("focused plan differs from source-bound open questions or budget")
    actual = [{k: j[k] for k in plan["jobs"][0]} for j in recorded["jobs"]] if plan["jobs"] else []
    # Execution groups jobs by model to avoid repeated server starts.
    expected_jobs = [j for mid in stage.models for j in plan["jobs"] if j["model_id"] == mid]
    if actual != expected_jobs or (not expected_jobs and recorded.get("jobs")):
        raise ValueError("focused jobs differ from the frozen plan")
    by_id = {e.id: e for e in examples}
    models = {m.id: m for m in manifest.models}
    observed = []
    for job in expected_jobs:
        model = models[job["model_id"]]
        attempted = [
            n
            for n in names
            if n.startswith(job["prefix"] + "/")
            and "/executions/execution-" in n
            and "/attempt-" in n
        ]
        if len(attempted) > 1:
            raise ValueError("focused request exceeded its one-attempt budget")
        observed.extend(
            read_partial_observations(
                read=read,
                names=names,
                prefix=job["prefix"],
                config=focused_config(manifest, stage, model, job, policy),
                examples=(by_id[job["example_id"]],),
                resources=resources,
                stage=plan["evidence_stage"],
                model=model,
                previous=before,
            )
        )
    return tuple(observed)


def verify_global_focused_budget(*, read, names, policy: FocusedResolutionPolicy):
    attempts = [
        n
        for n in names
        if n.startswith("stages/")
        and "/focused/" in n
        and "/executions/execution-" in n
        and "/attempt-" in n
    ]
    case_ids = set()
    for name in attempts:
        case_root = name.split("/executions/execution-", 1)[0]
        case_ids.add(
            json.loads(read(case_root + "/partial-request-plan.json"))["clause"]["clause_id"]
        )
    if (
        len(attempts) > policy.max_requests
        or len(case_ids) > policy.max_cases
        or len(attempts) * policy.max_output_tokens > policy.max_total_output_tokens
    ):
        raise ValueError("focused physical work exceeds the frozen run budget")
