"""Opt-in execution of the existing cascade stages with sparse question plans.

No changed voting thresholds, model roster or hidden reduced completion profile.
Planning is model-free and stops after the first stage: later selections depend
on answers not available during planning. Successful stage decisions are frozen.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification.consensus import ModelConsensusService
from standards_atlas.application.semantic_qualification.eligibility import (
    SemanticTaskEligibilityPolicy,
    eligibility_from_input,
)
from standards_atlas.application.semantic_qualification.mixed_consensus import (
    input_selection_fingerprint,
)
from standards_atlas.application.semantic_qualification.mixed_evidence import (
    CORE_REQUIRED_ATTRIBUTES,
    CompletionProfile,
    MixedConsensusReport,
    StagedPartialObservation,
)
from standards_atlas.application.semantic_qualification.partial_observations import (
    PartialObservation,
    ordered_attributes,
    validate_partial_response,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    _atomic_json,
    _run_lock,
    run_partial_proposals,
)
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialProposalConfig,
    PartialTaskResources,
    prepare_partial_request,
)
from standards_atlas.application.semantic_qualification.performance import RequestTiming
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    CascadeStage,
    ModelCandidate,
    QualificationMatrixManifest,
    cascade_unresolved_clause_ids,
)
from standards_atlas.application.semantic_qualification.response_identity import (
    require_response_identity,
)
from standards_atlas.application.semantic_qualification.taxonomy_decisions import (
    load_taxonomy_rules,
)


def completion_for_matrix(manifest: QualificationMatrixManifest) -> CompletionProfile:
    required = set(CORE_REQUIRED_ATTRIBUTES)
    for stage in manifest.execution.stages:
        policy = stage.resolution or manifest.execution.resolution
        if policy.escalate_on_process_function_disagreement:
            required.add("primary_process_function")
        if policy.escalate_on_process_set_disagreement:
            required.add("process_functions")
    return CompletionProfile(required_attributes=ordered_attributes(tuple(required)))


def partial_config_for_model(
    manifest: QualificationMatrixManifest,
    stage: CascadeStage,
    model: ModelCandidate,
) -> PartialProposalConfig:
    budget = model.generation.max_output_tokens or max(
        prompt.max_output_tokens for prompt in manifest.prompts_for_stage(stage)
    )
    return PartialProposalConfig(
        corpus_id=manifest.corpus_id,
        dataset_version=manifest.dataset_version,
        provider=model.provider,
        model=model.model_ref or model.id,
        prompt_version="taxonomy-partial-v2",
        max_tokens=budget,
        reasoning_enabled=model.generation.reasoning_mode == "enabled",
        retry_on_truncation=model.generation.retry_on_truncation,
        truncation_retry_max_tokens=model.generation.truncation_retry_max_tokens
        or max(1024, budget),
    )


def model_run_prefix(stage, model, examples, previous) -> str:
    """Keep resumed stage revisions separate when an earlier failure is repaired."""
    identity = structure_fingerprint(
        {
            "selection": [e.id for e in examples],
            "accepted_state": previous.fingerprint if previous else None,
        }
    )
    return f"stages/{stage.id}/models/{model.id}/run-{identity}"


def read_partial_observations(
    *,
    read: Callable[[str], bytes],
    names: set[str],
    prefix: str,
    config: PartialProposalConfig,
    examples: tuple[EvaluationExample, ...],
    resources: Path,
    stage: str,
    model: ModelCandidate,
    previous: MixedConsensusReport | None,
) -> tuple[StagedPartialObservation, ...]:
    """Verify logical observations against requests and raw response artifacts.

    The list of case directories is derived from the frozen selection, not an
    untrusted report glob. Retries/executions cannot be mistaken for new votes.
    """
    task_resources = PartialTaskResources.load(resources, config)
    accepted = {c.example_id: c.accepted_values for c in previous.clauses} if previous else {}
    policy = SemanticTaskEligibilityPolicy(
        supported_item_kinds=task_resources.task.supported_item_kinds,
        excluded_content_profiles=task_resources.task.excluded_content_profiles,
        alternative_tasks=task_resources.task.alternative_tasks,
    )
    results = []
    for example in examples:
        prepared = prepare_partial_request(
            config,
            example.id,
            example.input,
            task_resources,
            accepted_attributes=accepted.get(example.id),
            accepted_state_sha256=previous.fingerprint if previous else None,
        )
        directory = f"{prefix}/cases/{structure_fingerprint({'example_id': example.id})}"
        plan_path = f"{directory}/partial-request-plan.json"
        if plan_path not in names:
            raise ValueError("missing planned partial case in cascade artifacts")
        if json.loads(read(plan_path)) != prepared.plan.model_dump(mode="json"):
            raise ValueError("partial plan differs from verified cascade source or acceptance")
        path = f"{directory}/partial-observation.json"
        if path in names and not eligibility_from_input(policy, dict(example.input)).eligible:
            raise ValueError("ineligible clause cannot carry partial model observations")
        if path not in names:
            continue  # Planned, interrupted or ineligible is not a negative observation.
        obs = PartialObservation.model_validate_json(read(path))
        if (
            obs.plan != prepared.plan
            or obs.request_fingerprint != prepared.fingerprint
            or obs.provider != config.provider
            or obs.model != config.model
        ):
            raise ValueError("partial observation identity differs from request")
        if obs.outcome == "evaluated":
            from standards_atlas.application.semantic_qualification.request_builder import (
                serialize_generation_request,
            )

            if json.loads(read(f"{directory}/request.json")) != serialize_generation_request(
                prepared.request
            ):
                raise ValueError("stored partial request differs from regenerated request")
            response = json.loads(read(f"{directory}/response.json"))
            if (
                structure_fingerprint(response) != obs.response_sha256
                or response.get("value") != obs.values
            ):
                raise ValueError("partial response differs from observation or model identity")
            require_response_identity(
                response,
                requested_model=config.model,
                prompt_version=config.prompt_version,
                provider=config.provider,
            )
            validate_partial_response(obs.values, prepared.request.output_schema, prepared.plan)
        results.append(
            StagedPartialObservation(
                stage=stage,
                model_id=model.id,
                observation=obs,
                applicability_eligible=model.dimension_eligibility.applicability_presence,
            )
        )
    return tuple(results)


def _source_resources(resources: Path) -> dict[str, Any]:
    cfg = PartialProposalConfig(
        corpus_id="identity",
        dataset_version="identity",
        provider="identity",
        model="identity",
        prompt_version="taxonomy-partial-v2",
    )
    task = PartialTaskResources.load(resources, cfg)
    return {
        "task": task.task.model_dump(mode="json"),
        "schema": dict(task.schema),
        "prompt": {"system": task.prompt.system_prompt, "template": task.prompt.user_template},
        "rules": load_taxonomy_rules().model_dump(mode="json"),
    }


def _write_report(
    root: Path,
    report: MixedConsensusReport,
    stages: list[dict],
    *,
    execute: bool,
    timing: RequestTiming,
) -> dict:
    _atomic_json(root / "mixed-consensus-report.json", report.model_dump(mode="json"))
    total_timing = RequestTiming()
    for path in sorted(root.glob("stages/**/executions/execution-*/request-timing.json")):
        total_timing = total_timing.plus(RequestTiming.model_validate_json(path.read_bytes()))
    payload = {
        "schema_version": "1.0",
        "kind": "partial-cascade-report",
        "executed": execute,
        "matrix_id": report.matrix_id,
        "selection_sha256": report.selection_sha256,
        "completion_profile": report.completion_profile.model_dump(mode="json"),
        "consensus_sha256": report.fingerprint,
        "metrics": report.metrics,
        "stages": stages,
        "request_timing_current_invocation": timing.model_dump(mode="json"),
        "cascade_request_timing_all_executions": total_timing.model_dump(mode="json"),
        "applicability_gate_is_final_policy": False,
    }
    _atomic_json(root / "partial-cascade-report.json", payload)
    lines = [
        "# Taxonomy partial cascade",
        "",
        f"Matrix: `{report.matrix_id}`",
        "",
        f"Accounted clauses: **{report.clause_count}**; completed required decisions: "
        f"**{report.completed_count}**.",
        "",
        "Completion is not full enrichment or final applicability. Unknown gates never "
        "become negative policy outcomes.",
        "",
        "| Stage | Entered | Newly completed | Open |",
        "|---|---:|---:|---:|",
    ]
    for stage in stages:
        lines.append(
            f"| {stage['stage_id']} | {stage['entered']} | "
            f"{stage['newly_completed']} | {stage['unresolved']} |"
        )
    lines += ["", "## Mandatory review", ""]
    for item in report.clauses:
        if item.requires_review:
            lines.append(
                f"- `{item.document_key}/{item.clause_id}`: " + "; ".join(item.review_reasons)
            )
    (root / "partial-cascade-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def run_partial_cascade(
    *,
    manifest: QualificationMatrixManifest,
    examples: tuple[EvaluationExample, ...],
    output_directory: Path,
    resources: Path,
    execute: bool = False,
    gateway_context: Callable | None = None,
    progress: Callable[[str], None] | None = None,
    source_fingerprints: dict[str, str] | None = None,
    completion_profile: CompletionProfile | None = None,
) -> dict[str, Any]:
    """Execute the configured stage sequence with real per-attribute early exits.

    This is an explicit opt-in operational run, not a fresh-repeat qualification
    claim. Full-output/adjudicator/challenger runs remain on the existing command.
    """
    if manifest.execution.mode != "cascade" or not manifest.execution.stages:
        raise ValueError("partial cascade requires explicit cascade stages")
    if manifest.consensus.adjudication.enabled or manifest.challenger_qualification.enabled:
        raise ValueError("partial cascade does not run adjudicators or challenger matrices")
    if any(s.apply_to != "unresolved" for s in manifest.execution.stages[1:]):
        raise ValueError("later partial stages must apply to unresolved clauses")
    identifiers = [s.id for s in manifest.execution.stages] + [m.id for m in manifest.models]
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) for name in identifiers):
        raise ValueError("unsafe stage/model identifier")
    examples = tuple(replace(e, expected={}, tags=()) for e in examples)
    if not examples:
        raise ValueError("partial cascade selection must not be empty")
    profile = completion_profile or completion_for_matrix(manifest)
    model_by_id = {m.id: m for m in manifest.models}
    coordinates = [e.input["context"].get("clause_id") for e in examples]
    if len(set(coordinates)) != len(coordinates):
        raise ValueError("cascade routing requires globally unique clause ids")
    # Unique suffixed identity prevents comparison archives from masquerading as
    # the unchanged full-output matrix, even when reusing its models/thresholds.
    matrix_id = manifest.matrix_id + "--taxonomy-partial-v1"
    definition = {
        "schema_version": "1.0",
        "kind": "partial-cascade-plan",
        "matrix_id": matrix_id,
        "manifest": manifest.model_dump(mode="json"),
        "completion_profile": profile.model_dump(mode="json"),
        "selection_sha256": input_selection_fingerprint(examples),
        "source_fingerprints": source_fingerprints or {},
        "resources_sha256": structure_fingerprint(_source_resources(resources)),
        "operational_repetitions_per_model": 1,
        "fresh_repetition_qualification": False,
    }
    root = output_directory.resolve()
    for protected in (
        "data",
        "src/standards_atlas/resources",
        ".atlas/data/documents",
        ".atlas/data/knowledge-evidence",
    ):
        if root.is_relative_to(Path(protected).resolve()):
            raise ValueError("partial cascade output must be separate from canonical/public data")
    marker = root / "partial-cascade-plan.json"
    if root.exists() and not marker.is_file():
        raise ValueError("output exists without a matching partial cascade plan")
    root.mkdir(parents=True, exist_ok=True)
    with _run_lock(root):
        if marker.exists() and json.loads(marker.read_bytes()) != definition:
            raise ValueError("partial cascade identity changed; choose a new output directory")
        _atomic_json(marker, definition)
        _atomic_json(
            root / "partial-cascade-inputs.json", [{"id": e.id, "input": e.input} for e in examples]
        )
        _atomic_json(root / "partial-cascade-resources.json", _source_resources(resources))
        previous = None
        all_observations = []
        stages = []
        current_timing = RequestTiming()
        for stage in manifest.execution.stages:
            resolution = stage.resolution or manifest.execution.resolution
            pending = (
                set(e.id for e in examples)
                if previous is None
                else {c.example_id for c in previous.clauses if not c.completed}
            )
            if not pending:
                break
            selected = tuple(e for e in examples if e.id in pending)
            accepted = (
                {c.example_id: c.accepted_values for c in previous.clauses} if previous else {}
            )
            stage_model_count = len(
                {(model_by_id[k].provider, model_by_id[k].model_ref or k) for k in stage.models}
            )
            preflight = ModelConsensusService().evaluate_partial(
                matrix_id=matrix_id,
                corpus_id=manifest.corpus_id,
                stage_id=stage.id,
                examples=examples,
                observations=tuple(all_observations),
                resolution=resolution,
                consensus=manifest.consensus,
                resources=resources,
                completion_profile=profile,
                stage_model_count=stage_model_count,
                previous=previous,
            )
            needs_model = {c.example_id for c in preflight.clauses if not c.completed}
            requested_examples = tuple(e for e in selected if e.id in needs_model)
            stage_observations = []
            model_runs = []
            # Even a zero-request stage is evaluated. Fixed attributes are already
            # removed by PartialRequestPlan, not represented as fabricated votes.
            for model_id in stage.models if requested_examples else ():
                model = model_by_id[model_id]
                config = partial_config_for_model(manifest, stage, model)
                prefix = model_run_prefix(stage, model, requested_examples, previous)
                # Reject traversal before using manifest-owned identifiers as paths.
                if not (root / prefix).resolve().is_relative_to(root / "stages"):
                    raise ValueError("unsafe stage/model identifier")
                with ExitStack() as stack:

                    def gateway_factory(model=model, stack=stack):
                        if gateway_context is None:
                            raise ValueError("actual inference requires a gateway context")
                        return stack.enter_context(gateway_context(model))

                    model_report = run_partial_proposals(
                        config,
                        resources=resources,
                        output_directory=root / prefix,
                        examples=requested_examples,
                        execute=execute,
                        gateway_factory=gateway_factory,
                        source_fingerprints={"cascade-plan": structure_fingerprint(definition)},
                        accepted_decisions=accepted,
                        accepted_state_sha256=previous.fingerprint if previous else None,
                        progress=progress,
                    )
                current_timing = current_timing.plus(
                    RequestTiming.model_validate(model_report["request_timing"])
                )
                names = {
                    p.relative_to(root).as_posix()
                    for p in (root / prefix).rglob("*")
                    if p.is_file()
                }
                model_observations = read_partial_observations(
                    read=lambda name: (root / name).read_bytes(),
                    names=names,
                    prefix=prefix,
                    config=config,
                    examples=requested_examples,
                    resources=resources,
                    stage=stage.id,
                    model=model,
                    previous=previous,
                )
                stage_observations.extend(model_observations)
                model_runs.append({"model_id": model_id, "prefix": prefix})
            all_observations.extend(stage_observations)
            report = ModelConsensusService().evaluate_partial(
                matrix_id=matrix_id,
                corpus_id=manifest.corpus_id,
                stage_id=stage.id,
                examples=examples,
                observations=tuple(all_observations),
                resolution=resolution,
                consensus=manifest.consensus,
                resources=resources,
                completion_profile=profile,
                stage_model_count=len(
                    {(model_by_id[k].provider, model_by_id[k].model_ref or k) for k in stage.models}
                ),
                previous=previous,
            )
            unresolved, _ = cascade_unresolved_clause_ids(
                report.clauses,
                stage_clause_ids=tuple(c.clause_id for c in report.clauses),
                resolution=resolution,
            )
            path = f"stages/{stage.id}/mixed-stage-report.json"
            _atomic_json(root / path, report.model_dump(mode="json"))
            stages.append(
                {
                    "stage_id": stage.id,
                    "entered": len(selected),
                    "selected_example_ids": [e.id for e in selected],
                    "requested_example_ids": [e.id for e in requested_examples],
                    "newly_completed": (
                        report.completed_count - (previous.completed_count if previous else 0)
                    ),
                    "unresolved": len(unresolved),
                    "report": path,
                    "models": model_runs,
                    "consensus_sha256": report.fingerprint,
                }
            )
            previous = report
            _write_report(root, report, stages, execute=execute, timing=current_timing)
            if not execute:
                break
        if previous is None:
            raise ValueError("cascade produced no evaluated stage")
        payload = _write_report(root, previous, stages, execute=execute, timing=current_timing)
        write_partial_cascade_costs(root)
        return payload


def write_partial_cascade_costs(root: Path) -> dict[str, Any]:
    """Account for actual calls, including retired detail/stage revisions and retries.

    These are gateway/provider measurements, not end-to-end process wall time.
    Observation reuse is not a new inference; historical provider timings are
    already distinguished by RequestTiming and must not be relabelled fresh.
    """
    cascade, detail = RequestTiming(), RequestTiming()
    for path in sorted(root.glob("stages/**/executions/execution-*/request-timing.json")):
        cascade = cascade.plus(RequestTiming.model_validate_json(path.read_bytes()))
    for prefix in ("policy", "policy-history"):
        for path in sorted((root / prefix).glob("**/executions/execution-*/request-timing.json")):
            detail = detail.plus(RequestTiming.model_validate_json(path.read_bytes()))
    payload = {
        "schema_version": "1.0",
        "kind": "partial-cascade-costs",
        "scope": "all recorded executions; not total process wall time",
        "cascade": cascade.model_dump(mode="json"),
        "applicability_detail": detail.model_dump(mode="json"),
        "total": cascade.plus(detail).model_dump(mode="json"),
    }
    _atomic_json(root / "partial-cascade-costs.json", payload)
    return payload
