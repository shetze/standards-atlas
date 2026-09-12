"""Model-free, source-bound verification and immutable partial-cascade archiving."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import yaml

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.analysis_archive import (
    create_analysis_archive,
)
from standards_atlas.application.semantic_qualification.consensus import ModelConsensusService
from standards_atlas.application.semantic_qualification.mixed_consensus import (
    input_selection_fingerprint,
)
from standards_atlas.application.semantic_qualification.mixed_evidence import (
    CompletionProfile,
    MixedConsensusReport,
)
from standards_atlas.application.semantic_qualification.partial_cascade import (
    _source_resources,
    model_run_prefix,
    partial_config_for_model,
    read_partial_observations,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)


def verify_partial_cascade(
    *,
    read: Callable[[str], bytes],
    names: set[str],
    resources: Path,
) -> tuple[MixedConsensusReport, tuple[EvaluationExample, ...], QualificationMatrixManifest]:
    """Replay acceptance from original source, rules and verified partial responses.

    `read` must verify archive member hashes (or read the local run before it is
    archived). No files are written and no gateway is available to this reader.
    """
    plan = json.loads(read("partial-cascade-plan.json"))
    require_supported_schema("partial-cascade-run", plan.get("schema_version"))
    if plan.get("kind") != "partial-cascade-plan":
        raise ValueError("not a partial cascade plan")
    manifest = QualificationMatrixManifest.model_validate(plan["manifest"])
    profile = CompletionProfile.model_validate(plan["completion_profile"])
    source_resources = json.loads(read("partial-cascade-resources.json"))
    if structure_fingerprint(source_resources) != plan["resources_sha256"]:
        raise ValueError("partial cascade resource checksum mismatch")
    if source_resources != _source_resources(resources):
        raise ValueError(
            "archive source rules/task/prompt are not the installed supported versions"
        )
    payload = json.loads(read("partial-cascade-inputs.json"))
    if any(set(item) != {"id", "input"} for item in payload):
        raise ValueError("partial source snapshots must not contain expected labels or tags")
    examples = tuple(EvaluationExample(id=e["id"], input=e["input"], expected={}) for e in payload)
    if input_selection_fingerprint(examples) != plan["selection_sha256"]:
        raise ValueError("partial cascade source selection fingerprint mismatch")
    summary = json.loads(read("partial-cascade-report.json"))
    require_supported_schema("partial-cascade-run", summary.get("schema_version"))
    if summary.get("selection_sha256") != plan["selection_sha256"]:
        raise ValueError("partial cascade report belongs to another selection")
    previous = None
    observations = []
    stages = summary["stages"]
    if not stages or len(stages) > len(manifest.execution.stages):
        raise ValueError("invalid partial cascade stage count")
    model_by_id = {item.id: item for item in manifest.models}
    for index, recorded in enumerate(stages):
        stage = manifest.execution.stages[index]
        if recorded["stage_id"] != stage.id:
            raise ValueError("partial cascade stage order differs from frozen manifest")
        open_ids = (
            {c.example_id for c in previous.clauses if not c.completed}
            if previous
            else {e.id for e in examples}
        )
        selected = tuple(e for e in examples if e.id in open_ids)
        if recorded["selected_example_ids"] != [e.id for e in selected]:
            raise ValueError("partial cascade selection does not match unresolved decisions")
        resolution = stage.resolution or manifest.execution.resolution
        preflight = ModelConsensusService().evaluate_partial(
            matrix_id=manifest.matrix_id + "--taxonomy-partial-v1",
            corpus_id=manifest.corpus_id,
            stage_id=stage.id,
            examples=examples,
            observations=tuple(observations),
            resolution=resolution,
            consensus=manifest.consensus,
            resources=resources,
            completion_profile=profile,
            stage_model_count=len(
                {(model_by_id[k].provider, model_by_id[k].model_ref or k) for k in stage.models}
            ),
            previous=previous,
        )
        open_ids = {c.example_id for c in preflight.clauses if not c.completed}
        requested_examples = tuple(e for e in selected if e.id in open_ids)
        if recorded["requested_example_ids"] != [e.id for e in requested_examples]:
            raise ValueError("model request selection differs from preflight decisions")
        expected_models = (
            [
                {
                    "model_id": key,
                    "prefix": model_run_prefix(
                        stage, model_by_id[key], requested_examples, previous
                    ),
                }
                for key in stage.models
            ]
            if requested_examples
            else []
        )
        if recorded["models"] != expected_models:
            raise ValueError("partial cascade models differ from frozen stage")
        for item in expected_models:
            model = model_by_id[item["model_id"]]
            observations.extend(
                read_partial_observations(
                    read=read,
                    names=names,
                    prefix=item["prefix"],
                    config=partial_config_for_model(manifest, stage, model),
                    examples=requested_examples,
                    resources=resources,
                    stage=stage.id,
                    model=model,
                    previous=previous,
                )
            )
        resolution = stage.resolution or manifest.execution.resolution
        rebuilt = ModelConsensusService().evaluate_partial(
            matrix_id=manifest.matrix_id + "--taxonomy-partial-v1",
            corpus_id=manifest.corpus_id,
            stage_id=stage.id,
            examples=examples,
            observations=tuple(observations),
            resolution=resolution,
            consensus=manifest.consensus,
            resources=resources,
            completion_profile=profile,
            stage_model_count=len(
                {(model_by_id[k].provider, model_by_id[k].model_ref or k) for k in stage.models}
            ),
            previous=previous,
        )
        report_path = f"stages/{stage.id}/mixed-stage-report.json"
        if recorded["report"] != report_path:
            raise ValueError("partial stage report path differs from frozen stage")
        stored = MixedConsensusReport.model_validate_json(read(report_path))
        if stored != rebuilt or recorded["consensus_sha256"] != rebuilt.fingerprint:
            raise ValueError("mixed stage consensus differs from source/evidence replay")
        if (
            recorded["entered"] != len(selected)
            or recorded["newly_completed"]
            != rebuilt.completed_count - (previous.completed_count if previous else 0)
            or recorded["unresolved"] != rebuilt.clause_count - rebuilt.completed_count
        ):
            raise ValueError("partial stage accounting differs from acceptance decisions")
        previous = rebuilt
    result = MixedConsensusReport.model_validate_json(read("mixed-consensus-report.json"))
    if result != previous or result.fingerprint != summary["consensus_sha256"]:
        raise ValueError("mixed final consensus differs from last verified stage")
    if (
        result.metrics != summary["metrics"]
        or result.matrix_id != plan["matrix_id"]
        or result.completion_profile.model_dump(mode="json") != summary["completion_profile"]
    ):
        raise ValueError("partial cascade metrics/profile differ from verified decisions")
    return result, examples, manifest


def archive_partial_cascade(*, root: Path, archive_directory: Path, resources: Path) -> Path:
    """Use the existing checksummed qualification ZIP envelope; keep raw evidence."""
    root = root.resolve()
    archive_directory = archive_directory.resolve()
    if archive_directory.is_relative_to(root):
        raise ValueError("archive output must be separate from the mutable partial run")
    names = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if (root / ".partial-run.lock").exists():
        raise ValueError("cannot archive an actively written partial run")
    for name in names:
        if not (root / name).resolve().is_relative_to(root) or (root / name).is_symlink():
            raise ValueError("partial archive input contains an unsafe link")
    report, examples, manifest = verify_partial_cascade(
        read=lambda name: (root / name).read_bytes(),
        names=names,
        resources=resources,
    )
    from standards_atlas.application.semantic_qualification.mixed_applicability import (
        verify_mixed_applicability,
    )

    verify_mixed_applicability(
        read=lambda name: (root / name).read_bytes(),
        names=names,
        report=report,
        examples=examples,
        manifest=manifest,
    )
    # The envelope describes the actually executed partial task, not its full-
    # output control prompt. The frozen control configuration remains in the plan.
    executed_manifest = manifest.model_dump(mode="json")
    executed_manifest.update(
        matrix_id=report.matrix_id,
        task="semantic-attribute-observation",
        task_version="1.0.0",
        repetitions=1,
    )
    for prompt in executed_manifest["prompts"]:
        prompt.update(prompt_version="taxonomy-partial-v2", cbox_frame="taxonomy-grounded-v1")
    executed_manifest["review_imports"] = []
    path = root / "partial-cascade-matrix.yaml"
    path.write_text(yaml.safe_dump(executed_manifest, sort_keys=False), encoding="utf-8")
    return create_analysis_archive(
        output_directory=root,
        matrix_id=report.matrix_id,
        manifest_path=path,
        core_paths=tuple(
            p for p in sorted(root.rglob("*")) if p.is_file() and p.name != ".partial-run.lock"
        ),
        archive_directory=archive_directory,
        analysis_metrics={
            **report.metrics,
            "clause_count": report.clause_count,
            "review_count": report.clause_count - report.completed_count,
        },
        matrix_passed=None,
    )
