"""Evaluation CLI command group extracted without behavioral changes."""

from __future__ import annotations

import shutil
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
import yaml

from standards_atlas.adapters.llm import (
    CodexCliConfig,
    CodexCliLlmGateway,
    LlmConfig,
    OpenAICompatibleLlmGateway,
    RamaLamaServerError,
    RamaLamaServerManager,
)
from standards_atlas.adapters.mcp import (
    McpServerProcessError,
)
from standards_atlas.application.semantic_qualification.analysis_archive import (
    build_analysis_metrics,
    collect_qualification_input_members,
    create_analysis_archive,
    write_analysis_metrics,
    write_cascade_provenance,
    write_qualification_diagnostics,
)
from standards_atlas.application.semantic_qualification.applicability_framing import (
    build_applicability_framing_report,
    persist_applicability_framing_report,
)
from standards_atlas.application.semantic_qualification.applicability_hard_cases import (
    persist_applicability_prediction_snapshot,
)
from standards_atlas.application.semantic_qualification.challenger import (
    write_challenger_comparison,
)
from standards_atlas.application.semantic_qualification.prompt_comparison import (
    build_prompt_comparison_report,
    persist_prompt_comparison_report,
)
from standards_atlas.application.semantic_qualification.proposals import (
    ProposalProgress,
    ProposalRunConfig,
    historical_inference_duration,
    proposal_run_directory,
)
from standards_atlas.application.semantic_qualification.qualification_coverage import (
    QUALIFICATION_COVERAGE_FILENAME,
    build_qualification_coverage,
    persist_qualification_coverage,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    MatrixObservation,
    QualificationMatrixManifest,
    capture_resolved_dimensions,
    cascade_stage_unresolved_clause_ids,
    cascade_unresolved_clause_ids,
    effective_cascade_resolution,
    resolve_prompt_version,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QUALIFICATION_SELECTION_FILENAME,
    build_qualification_run_selection,
    load_qualification_run_selection,
    persist_qualification_run_selection,
)
from standards_atlas.application.services.evaluation import (
    AnnotationQualificationService,
    BaselineProposalGenerator,
    ModelConsensusService,
    ModelPromptQualificationService,
    SemanticAnnotationReviewService,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.cli.runtime_managers import managed_mcp_server


class _MatrixProposalProgress:
    """Render one continuously updated line for a matrix proposal run."""

    def __init__(
        self,
        *,
        candidate_index: int,
        candidate_total: int,
        label: str,
    ) -> None:
        self._candidate_index = candidate_index
        self._candidate_total = candidate_total
        self._label = label
        self._generated = 0
        self._failed = 0
        self._started_at = time.monotonic()
        self._last_width = 0

    def __call__(self, progress: ProposalProgress) -> None:
        if progress.status == "generated":
            self._generated += 1
        elif progress.status == "failed":
            self._failed += 1
        elapsed = max(time.monotonic() - self._started_at, 0.0)
        completed = self._generated + self._failed
        eta = None
        if completed > 0 and progress.total > completed:
            eta = elapsed / completed * (progress.total - completed)
        suffix = (
            f"[{progress.current:03d}/{progress.total:03d}] "
            f"ok={self._generated} failed={self._failed} "
            f"elapsed={_format_duration(elapsed)}"
        )
        if eta is not None:
            suffix += f" eta={_format_duration(eta)}"
        if progress.status == "retrying":
            suffix += f" retry={progress.attempt}/{progress.max_attempts}"
        line = (
            f"[Candidate {self._candidate_index:02d}/{self._candidate_total:02d}] "
            f"{self._label} {suffix}"
        )
        padding = " " * max(0, self._last_width - len(line))
        typer.echo(f"\r{line}{padding}", nl=False)
        self._last_width = len(line)

    def finish(self, *, generated: int, failed: int, skipped: int) -> None:
        elapsed = time.monotonic() - self._started_at
        line = (
            f"[Candidate {self._candidate_index:02d}/{self._candidate_total:02d}] "
            f"{self._label} complete: ok={generated} failed={failed} "
            f"skipped={skipped} elapsed={_format_duration(elapsed)}"
        )
        padding = " " * max(0, self._last_width - len(line))
        typer.echo(f"\r{line}{padding}")
        self._last_width = 0


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _cascade_reason_dimensions(reasons: tuple[str, ...]) -> set[str]:
    dimensions: set[str] = set()
    for reason in reasons:
        if reason in {
            "statement_function_confidence",
            "statement_function_resolver_confidence",
            "consensus_category",
        }:
            dimensions.add("statement_function")
        elif reason.startswith("applicability_"):
            dimensions.add("applicability")
        elif reason.startswith(("responsibility_", "role_relation_", "role_semantics_")):
            dimensions.add("responsibility")
    return dimensions


def _render_intermediate_resolution_summary(
    previous: dict[str, tuple[str, ...]],
    current: dict[str, tuple[str, ...]],
) -> None:
    for dimension in ("statement_function", "applicability", "responsibility"):
        candidates = {
            clause_id
            for clause_id, reasons in previous.items()
            if dimension in _cascade_reason_dimensions(reasons)
        }
        if not candidates:
            continue
        remaining = {
            clause_id
            for clause_id, reasons in current.items()
            if dimension in _cascade_reason_dimensions(reasons)
        }
        typer.echo(
            f"Intermediate resolution  : {dimension}="
            f"{len(candidates - remaining)}/{len(candidates)}"
        )


def _resolution_counts(
    resolutions: dict[str, dict[str, dict[str, object]]],
) -> dict[str, int]:
    dimensions = (
        "statement_function",
        "knowledge_kind",
        "applicability",
        "responsibility",
    )
    return {
        dimension: sum(dimension in clause for clause in resolutions.values())
        for dimension in dimensions
    }


def _count_reasons(reasons: dict[str, tuple[str, ...]]) -> dict[str, int]:
    counts = Counter(reason for values in reasons.values() for reason in values)
    return dict(sorted(counts.items()))


@evaluation_app.command("qualification-matrix")
def qualify_model_prompt_matrix(
    manifest_path: Annotated[Path, typer.Option("--manifest", exists=True, readable=True)],
    output_directory: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        ".atlas/data/evaluation/qualification"
    ),
    config: Annotated[
        Path, typer.Option("--config", exists=True, readable=True)
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    mcp_config: Annotated[
        Path,
        typer.Option(
            "--mcp-config",
            help="MCP YAML configuration used by Codex matrix candidates.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_MCP_CONFIG,
    mcp_autostart: Annotated[
        bool,
        typer.Option(
            "--mcp-autostart/--no-mcp-autostart",
            help="Start the MCP server automatically for Codex matrix candidates.",
            show_default=True,
        ),
    ] = True,
    mcp_autostop: Annotated[
        bool,
        typer.Option(
            "--mcp-autostop/--no-mcp-autostop",
            help="Stop the MCP server after the matrix if this command started it.",
            show_default=True,
        ),
    ] = True,
    resources: Annotated[
        Path, typer.Option("--resources", file_okay=False)
    ] = cli_defaults.DEFAULT_EVALUATION_RESOURCES,
    corpus_root: Annotated[Path, typer.Option("--corpus-root", file_okay=False)] = Path(
        ".atlas/data/evaluation/corpora"
    ),
    published_corpus_root: Annotated[
        Path, typer.Option("--published-corpus-root", file_okay=False)
    ] = Path("data/evaluation/corpora"),
    runs_output: Annotated[Path, typer.Option("--runs-output", file_okay=False)] = Path(
        ".atlas/data/evaluation/runs"
    ),
    metrics_output: Annotated[Path, typer.Option("--metrics-output", file_okay=False)] = Path(
        "local/evaluation/metrics"
    ),
    archive_output: Annotated[
        Path,
        typer.Option(
            "--archive-output",
            file_okay=False,
            help="Human-facing immutable qualification archive directory.",
        ),
    ] = Path("local/evaluation"),
    create_archive: Annotated[
        bool,
        typer.Option(
            "--create-archive/--no-create-archive",
            help="Create the immutable qualification-run archive after matrix evaluation.",
        ),
    ] = True,
    aggregate_only: Annotated[
        bool,
        typer.Option(
            "--aggregate-only",
            help="Only aggregate observations already declared in the manifest.",
        ),
    ] = False,
    include_optional_reasoning: Annotated[
        bool,
        typer.Option(
            "--include-optional-reasoning",
            help="Also execute reasoning modes marked optional.",
        ),
    ] = False,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help="Reuse completed proposals and generate only missing results (default).",
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Regenerate all proposals and recompute all derived results.",
        ),
    ] = False,
    recompute: Annotated[
        bool,
        typer.Option(
            "--recompute",
            help="Keep proposals and recompute metrics, qualification, and consensus only.",
        ),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option(
            "--no-cache",
            help="Bypass the LLM response cache while preserving proposal reuse.",
        ),
    ] = False,
    no_reuse: Annotated[
        bool,
        typer.Option(
            "--no-reuse",
            help="Regenerate proposals instead of reusing completed proposal results.",
        ),
    ] = False,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Run fresh inference: equivalent to --no-reuse --no-cache.",
        ),
    ] = False,
    fail_on_matrix_failure: Annotated[
        bool,
        typer.Option(
            "--fail-on-matrix-failure/--no-fail-on-matrix-failure",
            help=(
                "Exit with status 1 when qualification thresholds are not met; "
                "disable for orchestrated workflows that consume the reports."
            ),
            show_default=True,
        ),
    ] = True,
    limit: Annotated[
        int | None, typer.Option("--limit", min=1, help="Limit clauses per matrix run.")
    ] = None,
    max_tokens: Annotated[
        int | None,
        typer.Option("--max-tokens", min=1, help="Override prompt-specific output limit."),
    ] = None,
    challenger_source_manifest: Annotated[
        Path | None,
        typer.Option(
            "--challenger-source-manifest",
            exists=True,
            readable=True,
            hidden=True,
        ),
    ] = None,
    selected_example_ids_override: Annotated[
        list[str] | None,
        typer.Option("--selected-example-id", hidden=True),
    ] = None,
    challenger_sample_path: Annotated[
        Path | None,
        typer.Option("--challenger-sample-path", hidden=True),
    ] = None,
) -> None:
    """Execute and qualify the complete model/prompt matrix.

    The default mode is ``resume``: completed proposals are reused and missing
    results are generated. ``--overwrite`` regenerates proposals and all derived
    outputs. ``--recompute`` keeps proposals and rebuilds only metrics, matrix
    qualification, and consensus. ``--no-reuse`` regenerates proposals while still
    permitting LLM-cache hits; ``--no-cache`` bypasses only the LLM response cache.
    ``--fresh`` combines both for a true new inference run. Use ``--aggregate-only``
    only for observations already declared in the manifest.
    """
    active_server: RamaLamaServerManager | None = None
    active_mcp_lease = None
    cascade_stage_metrics: list[dict[str, object]] = []
    provenance_path: Path | None = None
    analysis_metrics_path: Path | None = None
    analysis_archive_path: Path | None = None
    try:
        selected_modes = sum((resume, overwrite, recompute))
        if selected_modes > 1:
            raise ValueError("--resume, --overwrite, and --recompute are mutually exclusive")
        run_mode = "overwrite" if overwrite else "recompute" if recompute else "resume"
        if (recompute or aggregate_only) and (no_cache or no_reuse or fresh):
            mode = "--recompute" if recompute else "--aggregate-only"
            raise ValueError(f"{mode} cannot be combined with --no-cache, --no-reuse, or --fresh")
        proposal_reuse_enabled = not (overwrite or no_reuse or fresh)
        llm_cache_enabled = not (no_cache or fresh)
        execution_policy = {
            "proposal_reuse": proposal_reuse_enabled,
            "llm_cache": llm_cache_enabled,
            "fresh_requested": fresh,
        }
        typer.echo(
            "Execution policy         : "
            f"proposal_reuse={'enabled' if proposal_reuse_enabled else 'disabled'}, "
            f"llm_cache={'enabled' if llm_cache_enabled else 'disabled'}"
        )
        manifest = QualificationMatrixManifest.load(manifest_path)
        for review_import in manifest.review_imports:
            proposal_candidates = tuple(
                review_import.run_directory.glob("*/evaluation.yaml")
            ) + tuple(review_import.run_directory.glob("*/evaluation.json"))
            review_documents = tuple(review_import.review_directory.glob("*.md"))
            if not proposal_candidates or not review_documents:
                if review_import.required:
                    missing = (
                        "proposal candidates" if not proposal_candidates else "Markdown reviews"
                    )
                    missing_path = (
                        review_import.run_directory
                        if not proposal_candidates
                        else review_import.review_directory
                    )
                    raise ValueError(f"required review import has no {missing}: {missing_path}")
                typer.echo(
                    f"Skipping optional review import: {review_import.run_directory}",
                    err=True,
                )
                continue
            SemanticAnnotationReviewService().import_reviews(
                review_directory=review_import.review_directory,
                run_directory=review_import.run_directory,
                local_corpus_root=review_import.local_corpus_root,
                corpus_id=manifest.corpus_id,
                overwrite=review_import.overwrite,
            )
        if aggregate_only:
            selection_path = (
                output_directory / manifest.matrix_id / QUALIFICATION_SELECTION_FILENAME
            )
            if not selection_path.is_file():
                raise ValueError(
                    "--aggregate-only requires a persisted qualification selection: "
                    f"{selection_path}"
                )
            run_selection = load_qualification_run_selection(selection_path)

        if not aggregate_only:
            observation_map = (
                {}
                if not proposal_reuse_enabled
                else {
                    (
                        item.prompt_id,
                        item.model_id,
                        item.reasoning_mode_id,
                        item.repetition,
                    ): item
                    for item in manifest.observations
                }
            )
            dataset, selected_examples, run_selection = build_qualification_run_selection(
                corpus_root=corpus_root,
                task=manifest.task,
                dataset_version=manifest.dataset_version,
                corpus_id=manifest.corpus_id,
                limit=limit,
                selected_example_ids=selected_example_ids_override,
            )
            selected_example_ids = tuple(example.id for example in selected_examples)
            selection_path = persist_qualification_run_selection(
                run_selection,
                output_directory / manifest.matrix_id / QUALIFICATION_SELECTION_FILENAME,
                corpus_root=corpus_root,
            )
            typer.echo(
                "Clause selection         : "
                f"{run_selection.selected_clause_count}/{run_selection.dataset_clause_count} "
                f"clauses ({selection_path})"
            )
            base_config = LlmConfig.load(config)
            if not llm_cache_enabled:
                base_config = replace(base_config, cache_directory=None)
            active_server = RamaLamaServerManager(base_config)
            active_server.stop()
            active_reasoning_modes = tuple(
                reasoning
                for reasoning in manifest.reasoning_modes
                if include_optional_reasoning or not reasoning.optional
            )
            model_by_id = {model.id: model for model in manifest.models}
            if manifest.execution.mode == "cascade":
                execution_stages = manifest.execution.stages
            else:
                execution_stages = (
                    type(
                        "FullMatrixStage",
                        (),
                        {
                            "id": "full-matrix",
                            "models": tuple(model_by_id),
                            "prompts": tuple(prompt.id for prompt in manifest.prompts),
                            "apply_to": "all",
                        },
                    )(),
                )
            candidate_total = sum(
                manifest.repetitions_for(model_by_id[model_id])
                * len(manifest.prompts_for_stage(stage))
                * len(active_reasoning_modes)
                for stage in execution_stages
                for model_id in stage.models
            )
            candidate_index = 0
            unresolved_clause_ids: tuple[str, ...] | None = None
            escalation_reasons: dict[str, tuple[str, ...]] = {}
            dimension_resolutions: dict[str, dict[str, dict[str, object]]] = {}
            for stage_index, stage in enumerate(execution_stages):
                stage_clause_ids = (
                    unresolved_clause_ids
                    if stage.apply_to == "unresolved"
                    else selected_example_ids
                )
                if stage.apply_to == "unresolved" and not stage_clause_ids:
                    typer.echo(f"Skipping cascade stage {stage.id}: no unresolved clauses")
                    break
                typer.echo(f"Matrix stage             : {stage.id}")
                stage_observation_keys: list[tuple[str, str, str, int]] = []
                stage_models = tuple(model_by_id[model_id] for model_id in stage.models)
                for model in stage_models:
                    model_repetitions = manifest.repetitions_for(model)
                    if model_repetitions == 0:
                        typer.echo(f"Skipping model {model.id} (repetitions=0)")
                        continue
                    if not model.model_ref:
                        raise ValueError(f"model {model.id} has no model_ref")
                    gateway = None
                    if run_mode != "recompute":
                        if active_server is not None:
                            active_server.stop()
                            active_server = None
                        if model.provider == "ramalama":
                            model_config = replace(
                                base_config,
                                model=model.model_ref,
                                server=replace(base_config.server, model=model.model_ref),
                            )
                            active_server = RamaLamaServerManager(model_config)
                            if model_config.server.enabled:
                                active_server.start()
                                runtime_status = active_server.status()
                                served_models = ", ".join(runtime_status.models) or "<none>"
                                typer.echo(
                                    "LLM runtime identity     : "
                                    f"requested={model.model_ref} served={served_models}"
                                )
                            gateway = OpenAICompatibleLlmGateway(model_config)
                        elif model.provider == "codex":
                            if active_mcp_lease is None:
                                mcp_manager = managed_mcp_server(mcp_config)
                                active_mcp_lease = mcp_manager.ensure_running(
                                    autostart=mcp_autostart,
                                    autostop=mcp_autostop,
                                )
                                active_mcp_lease.__enter__()
                            gateway = CodexCliLlmGateway(CodexCliConfig())
                        else:
                            raise ValueError(
                                "matrix model provider must be 'ramalama' or 'codex', "
                                f"got {model.provider!r} for {model.id}"
                            )
                    elif model.provider not in {"ramalama", "codex"}:
                        raise ValueError(
                            "matrix model provider must be 'ramalama' or 'codex', "
                            f"got {model.provider!r} for {model.id}"
                        )
                    for prompt in manifest.prompts_for_stage(stage):
                        prompt_version = resolve_prompt_version(
                            prompt, resources=resources, task=manifest.task
                        )
                        for reasoning in active_reasoning_modes:
                            for repetition in range(1, model_repetitions + 1):
                                candidate_index += 1
                                run_label = " / ".join(
                                    (
                                        model.id,
                                        prompt.id,
                                        reasoning.id,
                                        f"repeat {repetition}",
                                    )
                                )
                                progress_reporter = _MatrixProposalProgress(
                                    candidate_index=candidate_index,
                                    candidate_total=candidate_total,
                                    label=run_label,
                                )
                                run_root = (
                                    runs_output
                                    / "qualification-runs"
                                    / manifest.matrix_id
                                    / reasoning.id
                                    / f"repeat-{repetition}"
                                )
                                started = time.monotonic()
                                proposal_config = ProposalRunConfig(
                                    corpus_id=manifest.corpus_id,
                                    task=manifest.task,
                                    task_version=manifest.task_version,
                                    dataset_version=manifest.dataset_version,
                                    prompt_version=prompt_version,
                                    cbox_frame=prompt.cbox_frame,
                                    provider=model.provider,
                                    model=model.model_ref,
                                    seed=repetition,
                                    overwrite=not proposal_reuse_enabled,
                                    limit=None,
                                    include_example_ids=stage_clause_ids,
                                    max_tokens=(
                                        max_tokens
                                        or model.generation.max_output_tokens
                                        or prompt.max_output_tokens
                                    ),
                                    adaptive_interview=prompt.adaptive_interview,
                                    adaptive_question_max_tokens=(
                                        max_tokens
                                        or model.generation.adaptive_question_max_tokens
                                        or model.generation.max_output_tokens
                                        or prompt.max_output_tokens
                                    ),
                                    truncation_retry_max_tokens=(
                                        model.generation.truncation_retry_max_tokens
                                    ),
                                    retry_on_truncation=(model.generation.retry_on_truncation),
                                    reasoning_enabled=(
                                        reasoning.enabled
                                        if reasoning.id != "disabled"
                                        else model.generation.reasoning_mode == "enabled"
                                    ),
                                )
                                run_directory = proposal_run_directory(proposal_config, run_root)
                                if not proposal_reuse_enabled and run_directory.exists():
                                    shutil.rmtree(run_directory)
                                fresh_prediction_count = 0
                                cached_prediction_count = 0
                                reused_prediction_count = 0
                                if run_mode == "recompute":
                                    proposal_candidates = tuple(
                                        run_directory.glob("*/evaluation.yaml")
                                    ) + tuple(run_directory.glob("*/evaluation.json"))
                                    if not proposal_candidates:
                                        raise ValueError(
                                            "cannot recompute without proposal candidates: "
                                            f"{run_directory}"
                                        )
                                    generated = failed = skipped = 0
                                    reused_prediction_count = len(proposal_candidates)
                                    errors: tuple[str, ...] = ()
                                    progress_reporter.finish(
                                        generated=0, failed=0, skipped=len(proposal_candidates)
                                    )
                                else:
                                    if gateway is None:
                                        raise RuntimeError("proposal gateway was not initialized")
                                    result = BaselineProposalGenerator(gateway).run(
                                        proposal_config,
                                        resources=resources,
                                        corpus_root=corpus_root,
                                        output_root=run_root,
                                        progress=progress_reporter,
                                    )
                                    run_directory = result.run_directory
                                    generated = result.generated
                                    failed = result.failed
                                    skipped = result.skipped
                                    errors = result.errors
                                    fresh_prediction_count = result.fresh_predictions
                                    cached_prediction_count = result.cached_predictions
                                    reused_prediction_count = result.reused_predictions
                                    progress_reporter.finish(
                                        generated=generated, failed=failed, skipped=skipped
                                    )
                                if failed:
                                    failure_label = (
                                        f"{model.id}/{prompt.id}/{reasoning.id}/repeat-{repetition}"
                                    )
                                    typer.echo(
                                        "Proposal failures         : "
                                        f"{failure_label}: {failed} clause(s)",
                                        err=True,
                                    )
                                    for error in errors:
                                        typer.echo(f"  - {error}", err=True)
                                metric_dir = (
                                    metrics_output
                                    / manifest.matrix_id
                                    / model.id
                                    / prompt.id
                                    / reasoning.id
                                    / f"repeat-{repetition}"
                                )
                                _, qualification_path, _ = (
                                    AnnotationQualificationService().evaluate(
                                        corpus_id=manifest.corpus_id,
                                        run_directory=run_directory,
                                        local_corpus_root=corpus_root,
                                        published_corpus_root=published_corpus_root,
                                        output_directory=metric_dir,
                                        example_ids=stage_clause_ids,
                                    )
                                )
                                elapsed_duration_seconds = time.monotonic() - started
                                measured_predictions, measured_duration_seconds = (
                                    historical_inference_duration(
                                        run_directory, list(stage_clause_ids)
                                    )
                                )
                                if fresh_prediction_count > 0 and not (
                                    cached_prediction_count or reused_prediction_count
                                ):
                                    performance_source = "fresh"
                                    inference_duration_seconds = (
                                        result.fresh_inference_duration_seconds
                                    )
                                elif measured_predictions > 0:
                                    performance_source = (
                                        "recompute_historical"
                                        if run_mode == "recompute"
                                        else "historical_mixed"
                                    )
                                    inference_duration_seconds = measured_duration_seconds
                                else:
                                    performance_source = "not_measured"
                                    inference_duration_seconds = None
                                observation = MatrixObservation(
                                    prompt_id=prompt.id,
                                    model_id=model.id,
                                    reasoning_mode_id=reasoning.id,
                                    repetition=repetition,
                                    qualification_report=qualification_path,
                                    run_directory=run_directory,
                                    mean_duration_seconds=inference_duration_seconds,
                                    elapsed_duration_seconds=elapsed_duration_seconds,
                                    performance_measurement_source=performance_source,
                                    fresh_prediction_count=fresh_prediction_count,
                                    cached_prediction_count=cached_prediction_count,
                                    reused_prediction_count=reused_prediction_count,
                                    peak_memory_gb=model.declared_memory_gb,
                                )
                                observation_key = (prompt.id, model.id, reasoning.id, repetition)
                                observation_map[observation_key] = observation
                                stage_observation_keys.append(observation_key)

                if manifest.execution.mode == "cascade":
                    previous_escalation_reasons = escalation_reasons
                    configured_resolution = stage.resolution or manifest.execution.resolution
                    stage_resolution = effective_cascade_resolution(
                        configured_resolution,
                        review_majority_min_confidence=(
                            manifest.consensus.review_policy.accept_majority_min_confidence
                        ),
                    )
                    resolution_counts_before = _resolution_counts(dimension_resolutions)
                    entry_reasons = (
                        {clause_id: ("initial_stage",) for clause_id in stage_clause_ids}
                        if stage_index == 0
                        else {
                            clause_id: previous_escalation_reasons.get(clause_id, ())
                            for clause_id in stage_clause_ids
                        }
                    )
                    interim_manifest = QualificationMatrixManifest.model_validate(
                        {
                            **manifest.model_dump(mode="python"),
                            "observations": tuple(observation_map.values()),
                        }
                    )
                    interim_report, _, _, _ = ModelConsensusService().evaluate(
                        matrix_id=manifest.matrix_id,
                        corpus_id=manifest.corpus_id,
                        prompt_id=manifest.consensus.prompt_id,
                        reasoning_mode_id=manifest.consensus.reasoning_mode_id,
                        observations=interim_manifest.observations,
                        output_directory=(
                            output_directory / manifest.matrix_id / "cascade" / stage.id
                        ),
                        corpus_root=corpus_root,
                        min_models=stage_resolution.minimum_successful_models,
                        strong_threshold=manifest.consensus.strong_threshold,
                        majority_threshold=manifest.consensus.majority_threshold,
                        label_threshold=manifest.consensus.label_threshold,
                        prompt_selection=manifest.consensus.prompt_selection.model_dump(),
                        review_policy=manifest.consensus.review_policy.model_dump(),
                        adjudication=manifest.consensus.adjudication.model_dump(),
                        structural_priors=(manifest.consensus.structural_priors.model_dump()),
                        example_ids=stage_clause_ids,
                        model_dimension_eligibility=(interim_manifest.model_dimension_eligibility),
                        min_applicability_presence_models=(
                            stage_resolution.minimum_applicability_presence_models
                        ),
                    )
                    if stage_index == 0:
                        unresolved_clause_ids, escalation_reasons = cascade_unresolved_clause_ids(
                            interim_report.clauses,
                            stage_clause_ids=stage_clause_ids,
                            resolution=stage_resolution,
                        )
                        interim_by_id = {item.clause_id: item for item in interim_report.clauses}
                        for clause_id in stage_clause_ids:
                            clause = interim_by_id.get(clause_id)
                            if clause is None:
                                continue
                            captured = capture_resolved_dimensions(
                                cumulative_clause=clause,
                                stage_clause=clause,
                                previous_reasons=(),
                                remaining_reasons=escalation_reasons.get(clause_id, ()),
                                source=stage.id,
                                initial_stage=True,
                            )
                            dimension_resolutions.setdefault(clause_id, {}).update(captured)
                    else:
                        stage_only_observations = tuple(
                            observation_map[key] for key in stage_observation_keys
                        )
                        stage_report, _, _, _ = ModelConsensusService().evaluate(
                            matrix_id=manifest.matrix_id,
                            corpus_id=manifest.corpus_id,
                            prompt_id=manifest.consensus.prompt_id,
                            reasoning_mode_id=manifest.consensus.reasoning_mode_id,
                            observations=stage_only_observations,
                            output_directory=(
                                output_directory
                                / manifest.matrix_id
                                / "cascade"
                                / stage.id
                                / "stage-resolver"
                            ),
                            corpus_root=corpus_root,
                            min_models=1,
                            strong_threshold=manifest.consensus.strong_threshold,
                            majority_threshold=manifest.consensus.majority_threshold,
                            label_threshold=manifest.consensus.label_threshold,
                            prompt_selection=(manifest.consensus.prompt_selection.model_dump()),
                            review_policy=manifest.consensus.review_policy.model_dump(),
                            adjudication=manifest.consensus.adjudication.model_dump(),
                            structural_priors=(manifest.consensus.structural_priors.model_dump()),
                            example_ids=stage_clause_ids,
                            model_dimension_eligibility=(
                                interim_manifest.model_dimension_eligibility
                            ),
                        )
                        unresolved_clause_ids, escalation_reasons = (
                            cascade_stage_unresolved_clause_ids(
                                interim_report.clauses,
                                stage_report.clauses,
                                stage_clause_ids=stage_clause_ids,
                                previous_reasons=previous_escalation_reasons,
                                resolution=stage_resolution,
                            )
                        )
                        cumulative_by_id = {item.clause_id: item for item in interim_report.clauses}
                        stage_by_id = {item.clause_id: item for item in stage_report.clauses}
                        for clause_id in stage_clause_ids:
                            cumulative_clause = cumulative_by_id.get(clause_id)
                            stage_clause = stage_by_id.get(clause_id)
                            if cumulative_clause is None or stage_clause is None:
                                continue
                            resolver_clause = (
                                stage_clause
                                if stage_resolution.statement_function_resolution_mode
                                == "stage_resolver"
                                else cumulative_clause
                            )
                            captured = capture_resolved_dimensions(
                                cumulative_clause=cumulative_clause,
                                stage_clause=resolver_clause,
                                previous_reasons=previous_escalation_reasons.get(clause_id, ()),
                                remaining_reasons=escalation_reasons.get(clause_id, ()),
                                source=stage.id,
                            )
                            dimension_resolutions.setdefault(clause_id, {}).update(captured)
                        _render_intermediate_resolution_summary(
                            previous_escalation_reasons, escalation_reasons
                        )
                    reason_counts = Counter(
                        reason for reasons in escalation_reasons.values() for reason in reasons
                    )
                    typer.echo(
                        "Cascade unresolved       : "
                        f"{len(unresolved_clause_ids)} / {len(stage_clause_ids)}"
                    )
                    if reason_counts:
                        typer.echo(
                            "Cascade escalation     : "
                            + ", ".join(
                                f"{reason}={count}"
                                for reason, count in sorted(reason_counts.items())
                            )
                        )
                    resolution_counts_after = _resolution_counts(dimension_resolutions)
                    cascade_stage_metrics.append(
                        {
                            "stage_id": stage.id,
                            "configured_resolution": configured_resolution.model_dump(),
                            "effective_resolution": stage_resolution.model_dump(),
                            "entered_clause_count": len(stage_clause_ids),
                            "entered_clause_ids": list(stage_clause_ids),
                            "entry_reasons": {
                                key: list(value) for key, value in entry_reasons.items()
                            },
                            "entry_reason_counts": _count_reasons(entry_reasons),
                            "unresolved_clause_count": len(unresolved_clause_ids),
                            "unresolved_clause_ids": list(unresolved_clause_ids),
                            "exit_reasons": {
                                key: list(value) for key, value in escalation_reasons.items()
                            },
                            "exit_reason_counts": _count_reasons(escalation_reasons),
                            "resolution_counts_before": resolution_counts_before,
                            "resolution_counts_after": resolution_counts_after,
                            "newly_resolved_counts": {
                                dimension: resolution_counts_after[dimension]
                                - resolution_counts_before[dimension]
                                for dimension in resolution_counts_after
                            },
                        }
                    )
            provenance_path = write_cascade_provenance(
                output_directory=output_directory,
                matrix_id=manifest.matrix_id,
                manifest_path=manifest_path,
                run_mode=run_mode,
                execution_policy=execution_policy,
                stages=cascade_stage_metrics,
            )
            manifest = QualificationMatrixManifest.model_validate(
                {
                    **manifest.model_dump(mode="python"),
                    "observations": tuple(observation_map.values()),
                }
            )

        applicability_predictions_path = persist_applicability_prediction_snapshot(
            manifest, output_directory / manifest.matrix_id
        )
        report, json_path, markdown_path = ModelPromptQualificationService().evaluate(
            manifest,
            output_directory / manifest.matrix_id,
        )
        prompt_comparison = build_prompt_comparison_report(
            manifest=manifest,
            local_corpus_root=corpus_root,
            published_corpus_root=published_corpus_root,
        )
        prompt_comparison_paths = persist_prompt_comparison_report(
            prompt_comparison,
            output_directory / manifest.matrix_id,
        )
        applicability_framing = build_applicability_framing_report(
            manifest=manifest,
            golden_path=Path("local/review/applicability/2.0.0/applicability-golden-corpus.yaml"),
        )
        applicability_framing_paths = persist_applicability_framing_report(
            applicability_framing,
            output_directory / manifest.matrix_id,
        )
        consensus_paths: tuple[Path, Path, Path] | None = None
        if manifest.consensus.enabled:
            consensus_report, consensus_json, proposal_yaml, review_markdown = (
                ModelConsensusService().evaluate(
                    matrix_id=manifest.matrix_id,
                    corpus_id=manifest.corpus_id,
                    prompt_id=manifest.consensus.prompt_id,
                    reasoning_mode_id=manifest.consensus.reasoning_mode_id,
                    observations=manifest.observations,
                    output_directory=(manifest.consensus.output_directory / manifest.matrix_id),
                    corpus_root=corpus_root,
                    min_models=manifest.consensus.min_models,
                    strong_threshold=manifest.consensus.strong_threshold,
                    majority_threshold=manifest.consensus.majority_threshold,
                    label_threshold=manifest.consensus.label_threshold,
                    prompt_selection=manifest.consensus.prompt_selection.model_dump(),
                    review_policy=manifest.consensus.review_policy.model_dump(),
                    adjudication=manifest.consensus.adjudication.model_dump(),
                    structural_priors=manifest.consensus.structural_priors.model_dump(),
                    example_ids=selected_example_ids if not aggregate_only else None,
                    resolution_overrides=(
                        dimension_resolutions
                        if manifest.execution.mode == "cascade" and not aggregate_only
                        else None
                    ),
                    model_dimension_eligibility=manifest.model_dimension_eligibility,
                )
            )
            consensus_paths = (consensus_json, proposal_yaml, review_markdown)
            if provenance_path is None:
                provenance_path = write_cascade_provenance(
                    output_directory=output_directory,
                    matrix_id=manifest.matrix_id,
                    manifest_path=manifest_path,
                    run_mode=run_mode,
                    execution_policy=execution_policy,
                    stages=cascade_stage_metrics,
                )
            coverage = build_qualification_coverage(
                selection=run_selection,
                report=consensus_report,
            )
            coverage_path = persist_qualification_coverage(
                coverage,
                output_directory / manifest.matrix_id / QUALIFICATION_COVERAGE_FILENAME,
            )
            analysis_metrics = build_analysis_metrics(
                report=consensus_report,
                cascade_stages=cascade_stage_metrics,
                coverage=coverage,
            )
            analysis_metrics_path = write_analysis_metrics(
                output_directory=output_directory,
                matrix_id=manifest.matrix_id,
                metrics=analysis_metrics,
            )
            diagnostics_path = write_qualification_diagnostics(
                output_directory=output_directory,
                matrix_id=manifest.matrix_id,
                report=consensus_report,
                metrics=analysis_metrics,
            )
            challenger_paths: tuple[Path, ...] = ()
            if challenger_source_manifest is not None:
                source_manifest = QualificationMatrixManifest.load(challenger_source_manifest)
                challenger_paths = write_challenger_comparison(
                    source_manifest=source_manifest,
                    run_directory=output_directory / manifest.matrix_id,
                )
            manifest_payload = manifest_path.read_text(encoding="utf-8")
            qualification_input_members = collect_qualification_input_members(
                manifest_payload=yaml.safe_load(manifest_payload) or {},
                resources=resources,
                corpus_root=corpus_root,
                published_corpus_root=published_corpus_root,
            )
            qualification_input_members += (
                (config, "inputs/runtime/llm-config.yaml"),
                (mcp_config, "inputs/runtime/mcp-config.yaml"),
            )
            if create_archive:
                analysis_archive_path = create_analysis_archive(
                    output_directory=output_directory,
                    matrix_id=manifest.matrix_id,
                    manifest_path=manifest_path,
                    core_paths=(
                        json_path,
                        markdown_path,
                        consensus_json,
                        proposal_yaml,
                        review_markdown,
                        provenance_path,
                        analysis_metrics_path,
                        coverage_path,
                        diagnostics_path,
                        *prompt_comparison_paths,
                        *applicability_framing_paths,
                        applicability_predictions_path,
                        *challenger_paths,
                        *((challenger_sample_path,) if challenger_sample_path is not None else ()),
                    ),
                    cascade_directory=(output_directory / manifest.matrix_id / "cascade"),
                    analysis_metrics=analysis_metrics,
                    matrix_passed=report.passed,
                    execution_policy=execution_policy,
                    archive_directory=archive_output,
                    input_members=qualification_input_members,
                )
    except (
        McpServerProcessError,
        OSError,
        RamaLamaServerError,
        RuntimeError,
        ValueError,
    ) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    finally:
        if active_server is not None:
            active_server.stop()
        if active_mcp_lease is not None:
            active_mcp_lease.__exit__(None, None, None)
    typer.echo(f"Matrix result            : {'PASS' if report.passed else 'FAIL'}")
    typer.echo(f"Candidates               : {len(report.candidates)}")
    typer.echo(f"Pareto front             : {', '.join(report.pareto_front) or 'none'}")
    typer.echo(f"JSON report              : {json_path}")
    typer.echo(f"Markdown report          : {markdown_path}")
    if consensus_paths is not None:
        typer.echo(f"Consensus report         : {consensus_paths[0]}")
        typer.echo(f"Golden proposal          : {consensus_paths[1]}")
        typer.echo(f"HITL review queue        : {consensus_paths[2]}")
    if provenance_path is not None:
        typer.echo(f"Cascade provenance       : {provenance_path}")
    if analysis_metrics_path is not None:
        typer.echo(f"Analysis metrics         : {analysis_metrics_path}")
    if analysis_archive_path is not None:
        typer.echo(f"Analysis archive         : {analysis_archive_path}")
    if not report.passed and fail_on_matrix_failure:
        raise typer.Exit(code=1)
