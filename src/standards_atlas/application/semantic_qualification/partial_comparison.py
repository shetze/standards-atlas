"""Controlled first-stage comparisons; no parallel cascade or synthetic votes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.schema import require_current_payload, require_supported_schema
from standards_atlas.application.semantic_qualification.acceptance_profiles import (
    PartialAcceptanceProfile,
    with_acceptance_profile,
)
from standards_atlas.application.semantic_qualification.cascade_diagnostics import (
    describe_mixed_consensus,
)
from standards_atlas.application.semantic_qualification.cascade_replay_source import (
    CascadeReplaySource,
)
from standards_atlas.application.semantic_qualification.consensus import ModelConsensusService
from standards_atlas.application.semantic_qualification.partial_audit import (
    audit_partial_experiment,
)
from standards_atlas.application.semantic_qualification.partial_cascade import (
    DEFAULT_CASCADE_PROMPT,
    effective_cascade_configuration,
    partial_config_for_model,
    read_partial_observations,
    run_partial_cascade,
)
from standards_atlas.application.semantic_qualification.partial_cascade_archive import (
    verify_partial_cascade,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    _atomic_json,
    _run_lock,
    load_partial_inputs,
)
from standards_atlas.application.semantic_qualification.semantic_readiness import (
    evaluate_semantic_readiness,
)


def _output_is_separate(output: Path, inputs: tuple[Path, ...]):
    for source in inputs:
        if output == source.resolve() or (
            source.is_dir() and output.is_relative_to(source.resolve())
        ):
            raise ValueError("comparison output must be separate from inputs")
    for protected in (
        "data",
        "src/standards_atlas/resources",
        ".atlas/data/documents",
        ".atlas/data/knowledge-evidence",
    ):
        if output.is_relative_to(Path(protected).resolve()):
            raise ValueError("comparison output must be separate from canonical/public data")


def compare_partial_profiles(
    *, experiment: Path, profiles, output_directory: Path, resources: Path
):
    """Replay only the original first-stage evidence under candidate policies.

    Later requests would change when early acceptances change; those are NOT
    replayed as a fictitious end-to-end result. Focused jobs need new inference.
    """
    output = output_directory.resolve()
    _output_is_separate(output, (experiment,))
    if output.exists():
        raise ValueError("profile comparison needs a new output directory")
    profiles = tuple(profiles)
    if (
        not profiles
        or len({p.id for p in profiles}) != len(profiles)
        or any(p.id == "baseline" for p in profiles)
    ):
        raise ValueError("profiles must be nonempty with unique identities")
    if experiment.is_file() and experiment.suffix.lower() != ".zip":
        raise ValueError("profile comparison requires a complete experiment directory or ZIP")
    source = CascadeReplaySource(experiment)
    try:
        marker = source.locate("partial-cascade-plan.json", suffix="/partial-cascade-plan.json")
        if marker is None:
            raise ValueError("profile comparison requires the complete original experiment")
        prefix = marker.removesuffix("partial-cascade-plan.json")
        names = {n.removeprefix(prefix) for n in source.names if n.startswith(prefix)}
        if any(n.endswith(".partial-run.lock") for n in names):
            raise ValueError("cannot compare a cascade with an active writer")

        def read(name):
            return source.read(prefix + name)

        _, examples, manifest = verify_partial_cascade(read=read, names=names, resources=resources)
        definition = json.loads(read("partial-cascade-plan.json"))
        summary = json.loads(read("partial-cascade-report.json"))
        if not summary["executed"]:
            raise ValueError("a planned run supplies no baseline model evidence")
        stage = manifest.execution.stages[0]
        recorded = summary["stages"][0]
        selected_ids = set(recorded["requested_example_ids"])
        selected = tuple(e for e in examples if e.id in selected_ids)
        model_by_id = {m.id: m for m in manifest.models}
        prompt = definition.get("prompt_version", DEFAULT_CASCADE_PROMPT)
        observations = []
        for item in recorded["models"]:
            model = model_by_id[item["model_id"]]
            observations.extend(
                read_partial_observations(
                    read=read,
                    names=names,
                    prefix=item["prefix"],
                    config=partial_config_for_model(manifest, stage, model, prompt_version=prompt),
                    examples=selected,
                    resources=resources,
                    stage=stage.id,
                    model=model,
                    previous=None,
                )
            )
        rows, baseline = [], None
        reports = []
        for profile in (None, *profiles):
            resolution = with_acceptance_profile(
                stage.resolution or manifest.execution.resolution, profile
            )
            mixed = ModelConsensusService().evaluate_partial(
                matrix_id=manifest.matrix_id + "--taxonomy-partial-v1",
                corpus_id=manifest.corpus_id,
                stage_id=stage.id,
                examples=examples,
                observations=tuple(observations),
                resolution=resolution,
                consensus=manifest.consensus,
                resources=resources,
                stage_model_count=len(
                    {(model_by_id[m].provider, model_by_id[m].model_ref or m) for m in stage.models}
                ),
            )
            reports.append(mixed)
            if baseline is None:
                baseline = mixed
            changed = [
                {
                    "example_id": c.example_id,
                    "attribute": d.attribute,
                    "before_status": old.decision(d.attribute).status,
                    "after_status": d.status,
                    "before_value": old.decision(d.attribute).value,
                    "after_value": d.value,
                    "remaining_reasons": list(d.reasons),
                }
                for c, old in zip(mixed.clauses, baseline.clauses, strict=True)
                for d in c.decisions
                if (d.status, d.value)
                != (old.decision(d.attribute).status, old.decision(d.attribute).value)
            ]
            rows.append(
                {
                    "profile": profile.model_dump(mode="json") if profile else None,
                    "id": profile.id if profile else "baseline",
                    "diagnostics": describe_mixed_consensus(mixed, include_cases=True),
                    "changed_decisions": changed,
                    "focused_inference_not_executed": bool(profile and profile.focused_resolution),
                    "qualification_passed": False,
                }
            )
        hashes = dict(source.fingerprints)
        for name, digest in hashes.items():
            if hashlib.sha256(source.read(name)).hexdigest() != digest:
                raise ValueError("source changed during profile comparison")
        result = {
            "kind": "partial-profile-comparison",
            "schema_version": "1.0",
            "scope": "same stored first-stage observations; no new answers or future-stage replay",
            "source_prompt": prompt,
            "source_acceptance_profile": definition.get("acceptance_profile"),
            "source_fingerprints": hashes,
            "source_selection_sha256": baseline.selection_sha256,
            "source_evidence_verified": True,
            "selected_count": len(examples),
            "model_calls": 0,
            "original_acceptance_changed": False,
            "semantic_qualification_passed": False,
            "variants": rows,
        }
    finally:
        source.close()
    require_current_payload("partial-profile-comparison", result)
    output.mkdir(parents=True)
    _atomic_json(output / "partial-profile-comparison.json", result)
    for row, mixed in zip(rows, reports, strict=True):
        _atomic_json(
            output / row["id"] / "mixed-consensus-report.json", mixed.model_dump(mode="json")
        )
    return result


def compare_efficient_prompts(
    *,
    manifest,
    run: Path | None,
    dataset: Path | None,
    prompts: tuple[str, ...],
    output_directory: Path,
    resources: Path,
    limit: int = 50,
    execute: bool = False,
    gateway_context=None,
    acceptance_profile: PartialAcceptanceProfile | None = None,
    checks: Path | None = None,
    require_taxonomy_decisions: bool = False,
    progress=None,
):
    """Run the same four (or configured) Efficient models for each explicit prompt.

    Source sentinels are evaluated separately from format validity. This does not
    run the final applicability detail policy or certify its FP/FN budget.
    """
    if not prompts or len(set(prompts)) != len(prompts) or limit < 1:
        raise ValueError("unique prompt variants and a positive fixed limit are required")
    source = load_partial_inputs(run=run, dataset=dataset)
    if source.dataset_version != manifest.dataset_version or (
        source.corpus_id != "source-dataset" and source.corpus_id != manifest.corpus_id
    ):
        raise ValueError("manifest corpus/version differs from comparison source")
    examples = source.examples[:limit]
    # Validate every resource before creating outputs or starting a model.
    for prompt in prompts:
        effective_cascade_configuration(manifest, resources, prompt, acceptance_profile)
    output = output_directory.resolve()
    _output_is_separate(output, tuple(p for p in (run, dataset, checks) if p is not None))
    definition = {
        "schema_version": "1.0",
        "kind": "efficient-comparison-plan",
        "selection_sha256": structure_fingerprint(
            [{"id": e.id, "input": e.input} for e in examples]
        ),
        "manifest": manifest.model_dump(mode="json"),
        "prompts": list(prompts),
        "acceptance_profile": acceptance_profile.model_dump(mode="json")
        if acceptance_profile
        else None,
        "checks_sha256": hashlib.sha256(checks.read_bytes()).hexdigest() if checks else None,
        "require_taxonomy_decisions": require_taxonomy_decisions,
    }
    require_current_payload("efficient-comparison-plan", definition)
    marker = output / "efficient-comparison-plan.json"
    stored_definition = json.loads(marker.read_bytes()) if marker.is_file() else None
    if stored_definition is not None:
        require_supported_schema(
            "efficient-comparison-plan", stored_definition.get("schema_version")
        )
    if output.exists() and (not marker.is_file() or stored_definition != definition):
        raise ValueError("comparison identity changed; use a new output directory")
    output.mkdir(parents=True, exist_ok=True)
    with _run_lock(output):
        _atomic_json(marker, definition)
        rows = []
        for prompt in prompts:
            root = output / prompt
            result = run_partial_cascade(
                manifest=manifest,
                examples=examples,
                resources=resources,
                output_directory=root,
                execute=execute,
                gateway_context=gateway_context,
                source_fingerprints=source.fingerprints,
                prompt_version=prompt,
                acceptance_profile=acceptance_profile,
                stage_limit=1,
                require_taxonomy_decisions=require_taxonomy_decisions,
                progress=progress,
            )
            readiness = []
            if execute and checks is not None:
                for model in result["stages"][0]["models"]:
                    target = output / "readiness" / prompt / model["model_id"]
                    # Current reports can change after repaired failures; retain old diagnostics.
                    revision = structure_fingerprint(
                        {
                            "report": hashlib.sha256(
                                (root / model["prefix"] / "partial-run-report.json").read_bytes()
                            ).hexdigest(),
                            "checks": definition["checks_sha256"],
                        }
                    )
                    audit_dir = target / revision / "audit"
                    check_dir = target / revision / "checks"
                    if not audit_dir.exists():
                        audit_partial_experiment(
                            experiment=root / model["prefix"],
                            output_directory=audit_dir,
                            resources=resources,
                            run=run,
                            dataset=dataset,
                        )
                    if not check_dir.exists():
                        evaluate_semantic_readiness(
                            audit=audit_dir / "partial-audit.json",
                            checks=checks,
                            output_directory=check_dir,
                        )
                    readiness.append(
                        {
                            "model_id": model["model_id"],
                            "report": json.loads(
                                (check_dir / "semantic-readiness.json").read_bytes()
                            ),
                        }
                    )
            rows.append(
                {
                    "prompt": prompt,
                    "metrics": result["metrics"],
                    "diagnostics": result["diagnostics"],
                    "models": result["stages"][0]["diagnostics"]["models"],
                    "request_timing": result["cascade_request_timing_all_executions"],
                    "readiness": readiness,
                }
            )
            report = {
                "schema_version": "1.0",
                "kind": "efficient-prompt-comparison",
                "scope": "first stage only; fixed first-N selection, not representative",
                "executed": execute,
                "selected_count": len(examples),
                "applicability_gate_is_final_policy": False,
                "qualification_passed": False,
                "variants": rows,
            }
            require_current_payload("efficient-prompt-comparison", report)
            _atomic_json(output / "efficient-comparison.json", report)
    return report
