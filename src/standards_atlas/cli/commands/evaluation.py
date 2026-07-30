"""Command-line interface for Standards Atlas."""

from __future__ import annotations

import time
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.evaluation import EngineeringDocumentClauseProvider
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
from standards_atlas.application.qualification import (
    GoldenCorpusQualifier,
    QualificationRunReporter,
)
from standards_atlas.application.semantic_qualification.defaults import (
    STATEMENT_FUNCTION_PROMPT_VERSIONS,
)
from standards_atlas.application.services.evaluation import (
    AnnotationQualificationService,
    BaselineProposalGenerator,
    BenchmarkManifest,
    ClauseReferenceExtractionService,
    CorpusBuildConfig,
    EvaluationCorpusBuilder,
    EvaluationDatasetRepository,
    EvaluationMatrixRunner,
    EvaluationReporter,
    EvaluationRunner,
    MatrixObservation,
    ModelConsensusService,
    ModelPromptQualificationService,
    PromptRepository,
    ProposalProgress,
    ProposalRunConfig,
    QualificationMatrixManifest,
    SamplingStrategy,
    SemanticAnnotationReviewService,
    proposal_run_directory,
    resolve_prompt_version,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import (
    evaluation_app,
    qualification_app,
    semantic_evaluation_app,
)
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


@evaluation_app.command("corpus-build")
def build_evaluation_corpus(
    task: Annotated[str, typer.Option("--task")],
    version: Annotated[str, typer.Option("--version")],
    count: Annotated[int, typer.Option("--count", min=1)],
    workspace: Annotated[
        Path, typer.Option("--workspace", file_okay=False)
    ] = cli_defaults.DEFAULT_WORKSPACE,
    output: Annotated[
        Path, typer.Option("--output", file_okay=False)
    ] = cli_defaults.DEFAULT_EVALUATION_CORPUS_ROOT,
    strategy: Annotated[
        SamplingStrategy, typer.Option("--strategy")
    ] = cli_defaults.DEFAULT_CORPUS_STRATEGY,
    seed: Annotated[int, typer.Option("--seed")] = cli_defaults.DEFAULT_EVALUATION_SEED,
    include_text: Annotated[
        bool, typer.Option("--include-text/--hashes-only")
    ] = cli_defaults.DEFAULT_CORPUS_INCLUDE_TEXT,
    knowledge_domain: Annotated[
        str, typer.Option("--knowledge-domain")
    ] = cli_defaults.DEFAULT_KNOWLEDGE_DOMAIN,
    corpus_id: Annotated[str | None, typer.Option("--corpus-id")] = cli_defaults.DEFAULT_NONE,
) -> None:
    """Create an annotation-ready corpus from persisted clauses."""
    try:
        result = EvaluationCorpusBuilder(EngineeringDocumentClauseProvider(workspace)).build(
            CorpusBuildConfig(
                task=task,
                version=version,
                count=count,
                strategy=strategy,
                seed=seed,
                include_text=include_text,
                knowledge_domain=knowledge_domain,
                corpus_id=corpus_id,
            ),
            output,
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Corpus clauses          : {result.clause_count}")
    typer.echo(f"Dataset                 : {result.dataset_path}")
    typer.echo(f"Manifest                : {result.manifest_path}")


@evaluation_app.command("annotations-propose")
def propose_evaluation_annotations(
    corpus_id: Annotated[
        str,
        typer.Option(
            "--corpus-id",
            help="Corpus identifier below --corpus-root.",
        ),
    ],
    task: Annotated[
        str,
        typer.Option(
            "--task",
            help="Semantic task identifier.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_TASK,
    task_version: Annotated[
        str,
        typer.Option(
            "--task-version",
            help="Version of the semantic task contract and taxonomy.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_TASK_VERSION,
    dataset_version: Annotated[
        str,
        typer.Option(
            "--dataset-version",
            help="Version of the corpus dataset to load.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_DATASET_VERSION,
    prompt_version: Annotated[
        str,
        typer.Option(
            "--prompt-version",
            help=(
                "Prompt variant. Available for statement-function-classification: "
                + ", ".join(STATEMENT_FUNCTION_PROMPT_VERSIONS)
                + "."
            ),
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_PROMPT_VERSION,
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help="Provider-specific model identifier.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_MODEL,
    provider: Annotated[
        str,
        typer.Option(
            "--provider",
            help="LLM provider: ramalama or codex.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_PROVIDER,
    corpus_root: Annotated[
        Path,
        typer.Option(
            "--corpus-root",
            file_okay=False,
            help="Root directory containing evaluation corpora.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_CORPUS_ROOT,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            file_okay=False,
            help="Root directory for evaluation runs and reports.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_OUTPUT,
    resources: Annotated[
        Path,
        typer.Option(
            "--resources",
            file_okay=False,
            help="Root directory containing semantic tasks and prompts.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_RESOURCES,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="LLM YAML configuration used by the ramalama provider.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    mcp_config: Annotated[
        Path,
        typer.Option(
            "--mcp-config",
            help="MCP YAML configuration used by the Codex provider.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_MCP_CONFIG,
    mcp_autostart: Annotated[
        bool,
        typer.Option(
            "--mcp-autostart/--no-mcp-autostart",
            help="Start the MCP server automatically for Codex runs.",
            show_default=True,
        ),
    ] = True,
    mcp_autostop: Annotated[
        bool,
        typer.Option(
            "--mcp-autostop/--no-mcp-autostop",
            help="Stop the MCP server after Codex if this command started it.",
            show_default=True,
        ),
    ] = True,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Regenerate evaluation artifacts that already exist."),
    ] = cli_defaults.DEFAULT_FALSE,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Maximum number of pending clauses to process."),
    ] = cli_defaults.DEFAULT_NONE,
    max_tokens: Annotated[
        int,
        typer.Option(
            "--max-tokens", min=1, help="Maximum completion tokens per clause.", show_default=True
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_MAX_TOKENS,
    retry_attempts: Annotated[
        int,
        typer.Option(
            "--retry-attempts",
            min=1,
            help="Attempts for retryable provider failures.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_RETRY_ATTEMPTS,
    retry_backoff_seconds: Annotated[
        float,
        typer.Option(
            "--retry-backoff-seconds",
            min=0.0,
            help="Delay between retry attempts in seconds.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_EVALUATION_RETRY_BACKOFF_SECONDS,
    retry_timeouts: Annotated[
        bool,
        typer.Option(
            "--retry-timeouts/--no-retry-timeouts",
            help="Retry deterministic request timeouts as transient failures.",
            show_default=True,
        ),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Generate resumable baseline proposals for a local evaluation corpus.

    Prompt variants for ``statement-function-classification``:

    - ``content-only-v1``
    - ``structure-aware-v1``
    - ``evidence-first-v1``
    - ``conservative-v1``
    """
    try:
        mcp_guard = nullcontext()
        if provider == "codex":
            gateway = CodexCliLlmGateway(CodexCliConfig())
            mcp_manager = managed_mcp_server(mcp_config)
            mcp_guard = mcp_manager.ensure_running(
                autostart=mcp_autostart,
                autostop=mcp_autostop,
            )
        elif provider == cli_defaults.DEFAULT_EVALUATION_PROVIDER:
            llm_config = LlmConfig.load(config)
            server = RamaLamaServerManager(llm_config)
            if llm_config.server.enabled and not server.status().running:
                server.start()
            gateway = OpenAICompatibleLlmGateway(llm_config)
        else:
            raise ValueError("provider must be 'ramalama' or 'codex'")

        def show_progress(item) -> None:
            location = item.document_key
            if item.reference:
                location += f":{item.reference}"
            if item.title:
                location += f" — {item.title}"
            elapsed = f" ({item.elapsed_seconds:.1f}s)" if item.elapsed_seconds is not None else ""
            retry = (
                f" attempt {item.attempt}/{item.max_attempts}"
                if item.attempt is not None and item.max_attempts is not None
                else ""
            )
            line = (
                f"[{item.current:>3}/{item.total:<3}] "
                f"{item.status:<10} {location} [{item.example_id}]"
                f"{retry}{elapsed}"
            )
            if item.detail:
                line += f" — {item.detail}"
            typer.echo(line, err=item.status in {"failed", "retrying"})

        with mcp_guard:
            result = BaselineProposalGenerator(gateway).run(
                ProposalRunConfig(
                    corpus_id=corpus_id,
                    task=task,
                    task_version=task_version,
                    dataset_version=dataset_version,
                    prompt_version=prompt_version,
                    provider=provider,
                    model=model,
                    overwrite=overwrite,
                    limit=limit,
                    max_tokens=max_tokens,
                    retry_attempts=retry_attempts,
                    retry_backoff_seconds=retry_backoff_seconds,
                    retry_timeouts=retry_timeouts,
                ),
                resources=resources,
                corpus_root=corpus_root,
                output_root=output,
                progress=show_progress,
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
    typer.echo(f"Generated                : {result.generated}")
    typer.echo(f"Skipped                  : {result.skipped}")
    typer.echo(f"Failed                   : {result.failed}")
    typer.echo(f"Run directory            : {result.run_directory}")
    for error in result.errors:
        typer.echo(error, err=True)


@evaluation_app.command("references-extract")
def extract_clause_references(
    knowledge_domain: Annotated[
        str,
        typer.Option("--knowledge-domain", help="KnowledgeDomain owning the documents."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", file_okay=False, help="EngineeringDocument workspace."),
    ] = Path(".atlas"),
    output_root: Annotated[
        Path,
        typer.Option("--output", file_okay=False, help="Local reference-analysis root."),
    ] = Path("local/evaluation/references"),
    document: Annotated[
        list[str] | None,
        typer.Option("--document", help="Limit extraction to one or more document keys."),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace existing reference analyses."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Extract and resolve same-document clause references without an LLM."""
    try:
        result = ClauseReferenceExtractionService().run(
            workspace=workspace,
            knowledge_domain=knowledge_domain,
            output_root=output_root,
            document_keys=tuple(document or ()),
            overwrite=overwrite,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Documents                : {result.documents}")
    typer.echo(f"Clauses analysed         : {result.clauses}")
    typer.echo(f"References               : {result.references}")
    typer.echo(f"Resolved                 : {result.resolved}")
    typer.echo(f"Needs attention          : {result.unresolved}")
    typer.echo(f"Output root              : {result.output_root}")


@evaluation_app.command("annotations-review-export")
def export_annotation_reviews(
    run_directory: Annotated[
        Path,
        typer.Option("--run", exists=True, file_okay=False, help="Proposal run directory."),
    ],
    review_directory: Annotated[
        Path,
        typer.Option("--reviews", file_okay=False, help="Local Markdown review directory."),
    ],
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace existing Markdown reviews."),
    ] = cli_defaults.DEFAULT_FALSE,
    reference_root: Annotated[
        Path,
        typer.Option(
            "--reference-root",
            file_okay=False,
            help="Local clause-reference analyses included in HITL context.",
        ),
    ] = Path("local/evaluation/references"),
) -> None:
    """Export proposal candidates as editable local Markdown reviews."""
    try:
        result = SemanticAnnotationReviewService().export_run(
            run_directory=run_directory,
            review_directory=review_directory,
            overwrite=overwrite,
            reference_root=reference_root,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Exported                 : {result.exported}")
    typer.echo(f"Skipped                  : {result.skipped}")
    typer.echo(f"Review directory         : {result.review_directory}")


@evaluation_app.command("annotations-review-import")
def import_annotation_reviews(
    corpus_id: Annotated[str, typer.Option("--corpus-id", help="Stable corpus identifier.")],
    run_directory: Annotated[
        Path,
        typer.Option("--run", exists=True, file_okay=False, help="Proposal run directory."),
    ],
    review_directory: Annotated[
        Path,
        typer.Option("--reviews", exists=True, file_okay=False, help="Markdown review directory."),
    ],
    local_corpus_root: Annotated[
        Path,
        typer.Option(
            "--local-corpus-root",
            file_okay=False,
            help="Root for local reviewed corpus annotations.",
        ),
    ] = Path("local/evaluation/corpora"),
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace differing local reviewed annotations."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Validate Markdown reviews and import reviewed local annotations."""
    try:
        result = SemanticAnnotationReviewService().import_reviews(
            review_directory=review_directory,
            run_directory=run_directory,
            local_corpus_root=local_corpus_root,
            corpus_id=corpus_id,
            overwrite=overwrite,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Imported                 : {result.imported}")
    typer.echo(f"Skipped                  : {result.skipped}")
    for path in result.annotation_paths:
        typer.echo(f"Annotation               : {path}")


@evaluation_app.command("annotations-publish")
def publish_annotation_reviews(
    corpus_id: Annotated[str, typer.Option("--corpus-id", help="Stable corpus identifier.")],
    local_corpus_root: Annotated[
        Path,
        typer.Option("--local-corpus-root", file_okay=False),
    ] = Path("local/evaluation/corpora"),
    published_corpus_root: Annotated[
        Path,
        typer.Option("--published-corpus-root", file_okay=False),
    ] = Path("data/evaluation/corpora"),
    publish_manifest: Annotated[
        bool,
        typer.Option("--manifest/--no-manifest", help="Publish the corpus manifest as well."),
    ] = True,
) -> None:
    """Publish all reviewed local annotations into reproducible project data."""
    try:
        result = SemanticAnnotationReviewService().publish_reviews(
            corpus_id=corpus_id,
            local_corpus_root=local_corpus_root,
            published_corpus_root=published_corpus_root,
            publish_manifest=publish_manifest,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Published                : {result.published}")
    if result.manifest_path is not None:
        typer.echo(f"Corpus manifest          : {result.manifest_path}")


@evaluation_app.command("annotations-metrics")
def evaluate_annotation_metrics(
    corpus_id: Annotated[str, typer.Option("--corpus-id")],
    run_directory: Annotated[
        Path, typer.Option("--run", exists=True, file_okay=False, readable=True)
    ],
    local_corpus_root: Annotated[Path, typer.Option("--local-corpus-root", file_okay=False)] = Path(
        "local/evaluation/corpora"
    ),
    published_corpus_root: Annotated[
        Path, typer.Option("--published-corpus-root", file_okay=False)
    ] = Path("data/evaluation/corpora"),
    output_directory: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "local/evaluation/metrics"
    ),
) -> None:
    """Resolve corpus evidence and calculate Gold, Silver, and structure metrics."""
    try:
        report, json_path, markdown_path = AnnotationQualificationService().evaluate(
            corpus_id=corpus_id,
            run_directory=run_directory,
            local_corpus_root=local_corpus_root,
            published_corpus_root=published_corpus_root,
            output_directory=output_directory / corpus_id / run_directory.name,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Predictions              : {report.coverage.predictions}")
    typer.echo(f"Gold agreement F1        : {report.gold_agreement.micro_f1:.4f}")
    typer.echo(f"Silver agreement F1      : {report.silver_agreement.micro_f1:.4f}")
    typer.echo(f"Structure agreement F1   : {report.structure_agreement.micro_f1:.4f}")
    typer.echo(f"JSON report              : {json_path}")
    typer.echo(f"Markdown report          : {markdown_path}")


@evaluation_app.command("qualification-matrix")
def qualify_model_prompt_matrix(
    manifest_path: Annotated[Path, typer.Option("--manifest", exists=True, readable=True)],
    output_directory: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "local/evaluation/qualification"
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
        "local/evaluation/corpora"
    ),
    published_corpus_root: Annotated[
        Path, typer.Option("--published-corpus-root", file_okay=False)
    ] = Path("data/evaluation/corpora"),
    runs_output: Annotated[Path, typer.Option("--runs-output", file_okay=False)] = Path(
        "local/evaluation"
    ),
    metrics_output: Annotated[Path, typer.Option("--metrics-output", file_okay=False)] = Path(
        "local/evaluation/metrics"
    ),
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
    limit: Annotated[
        int | None, typer.Option("--limit", min=1, help="Limit clauses per matrix run.")
    ] = None,
    max_tokens: Annotated[
        int | None,
        typer.Option("--max-tokens", min=1, help="Override prompt-specific output limit."),
    ] = None,
) -> None:
    """Execute and qualify the complete model/prompt matrix.

    The default mode is ``resume``: completed proposals are reused and missing
    results are generated. ``--overwrite`` regenerates proposals and all derived
    outputs. ``--recompute`` keeps proposals and rebuilds only metrics, matrix
    qualification, and consensus. Use ``--aggregate-only`` only for observations
    already declared in the manifest.
    """
    active_server: RamaLamaServerManager | None = None
    active_mcp_lease = None
    try:
        selected_modes = sum((resume, overwrite, recompute))
        if selected_modes > 1:
            raise ValueError("--resume, --overwrite, and --recompute are mutually exclusive")
        run_mode = "overwrite" if overwrite else "recompute" if recompute else "resume"
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
        if not aggregate_only:
            observation_map = {
                (
                    item.prompt_id,
                    item.model_id,
                    item.reasoning_mode_id,
                    item.repetition,
                ): item
                for item in manifest.observations
            }
            base_config = LlmConfig.load(config)
            active_server = RamaLamaServerManager(base_config)
            active_server.stop()
            active_reasoning_modes = tuple(
                reasoning
                for reasoning in manifest.reasoning_modes
                if include_optional_reasoning or not reasoning.optional
            )
            candidate_total = sum(
                manifest.repetitions_for(model)
                * len(manifest.prompts)
                * len(active_reasoning_modes)
                for model in manifest.models
            )
            candidate_index = 0
            for model in manifest.models:
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
                model_repetitions = manifest.repetitions_for(model)
                for prompt in manifest.prompts:
                    prompt_version = resolve_prompt_version(prompt, resources=resources)
                    for reasoning in active_reasoning_modes:
                        for repetition in range(1, model_repetitions + 1):
                            candidate_index += 1
                            run_label = (
                                f"{model.id} / {prompt.id} / {reasoning.id} / repeat {repetition}"
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
                                task="statement-function-classification",
                                task_version=manifest.task_version,
                                dataset_version=manifest.dataset_version,
                                prompt_version=prompt_version,
                                provider=model.provider,
                                model=model.model_ref,
                                seed=repetition,
                                overwrite=run_mode == "overwrite",
                                limit=limit,
                                max_tokens=max_tokens or prompt.max_output_tokens,
                            )
                            if run_mode == "recompute":
                                run_directory = proposal_run_directory(proposal_config, run_root)
                                proposal_candidates = tuple(
                                    run_directory.glob("*/evaluation.yaml")
                                ) + tuple(run_directory.glob("*/evaluation.json"))
                                if not proposal_candidates:
                                    raise ValueError(
                                        "cannot recompute without proposal candidates: "
                                        f"{run_directory}"
                                    )
                                generated = failed = skipped = 0
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
                            _, qualification_path, _ = AnnotationQualificationService().evaluate(
                                corpus_id=manifest.corpus_id,
                                run_directory=run_directory,
                                local_corpus_root=corpus_root,
                                published_corpus_root=published_corpus_root,
                                output_directory=metric_dir,
                            )
                            observation = MatrixObservation(
                                prompt_id=prompt.id,
                                model_id=model.id,
                                reasoning_mode_id=reasoning.id,
                                repetition=repetition,
                                qualification_report=qualification_path,
                                run_directory=run_directory,
                                mean_duration_seconds=time.monotonic() - started,
                                peak_memory_gb=model.declared_memory_gb,
                            )
                            observation_map[(prompt.id, model.id, reasoning.id, repetition)] = (
                                observation
                            )
            manifest = QualificationMatrixManifest.model_validate(
                {
                    **manifest.model_dump(mode="python"),
                    "observations": tuple(observation_map.values()),
                }
            )

        report, json_path, markdown_path = ModelPromptQualificationService().evaluate(
            manifest,
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
                )
            )
            consensus_paths = (consensus_json, proposal_yaml, review_markdown)
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
    if not report.passed:
        raise typer.Exit(code=1)


@evaluation_app.command("benchmark")
def run_evaluation_matrix(
    manifest_path: Annotated[
        Path,
        typer.Option("--manifest", exists=True, readable=True),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
) -> None:
    """Execute the prompt/model matrix declared by a benchmark manifest."""
    llm_config = LlmConfig.load(config)
    server = RamaLamaServerManager(llm_config)
    try:
        manifest = BenchmarkManifest.load(manifest_path)
        if llm_config.server.enabled and not server.status().running:
            server.start()
        result = EvaluationMatrixRunner(
            EvaluationRunner(OpenAICompatibleLlmGateway(llm_config))
        ).run(manifest)
        report_path = EvaluationReporter().write_matrix_summary(
            result.runs,
            manifest.output / "matrix-summary.json",
            manifest_hash=result.manifest_hash,
            include_case_details=manifest.include_case_details,
        )
    except (OSError, ValueError, RamaLamaServerError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    for run in result.runs:
        typer.echo(
            f"{run.prompt_version} / {run.model}: "
            f"F1={run.metrics.f1:.4f}, schema={run.metrics.schema_valid_rate:.4f}"
        )
    typer.echo(f"Matrix report           : {report_path}")
    typer.echo(f"Manifest hash           : {result.manifest_hash}")


@semantic_evaluation_app.command("run")
def run_semantic_evaluation(
    task: Annotated[str, typer.Option("--task", help="Semantic task identifier.")],
    prompt_version: Annotated[str, typer.Option("--prompt-version")],
    dataset_version: Annotated[str, typer.Option("--dataset-version")],
    model: Annotated[
        list[str] | None,
        typer.Option("--model", help="Model identifier; repeat to compare models."),
    ] = cli_defaults.DEFAULT_NONE,
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    resources: Annotated[
        Path,
        typer.Option("--resources", exists=True, file_okay=False),
    ] = cli_defaults.DEFAULT_EVALUATION_RESOURCES,
    output: Annotated[
        Path,
        typer.Option("--output", file_okay=False),
    ] = cli_defaults.DEFAULT_SEMANTIC_EVALUATION_OUTPUT,
) -> None:
    llm_config = LlmConfig.load(config)
    server = RamaLamaServerManager(llm_config)
    try:
        if llm_config.server.enabled and not server.status().running:
            server.start()
        prompt = PromptRepository(resources / "prompts").load(task, prompt_version)
        dataset = EvaluationDatasetRepository(resources / "corpora").load(task, dataset_version)
        runner = EvaluationRunner(OpenAICompatibleLlmGateway(llm_config))
        models = tuple(model or (llm_config.model,))
        runs = runner.benchmark(prompt, dataset, models)
        reporter = EvaluationReporter()
        paths = tuple(reporter.write(run, output) for run in runs)
        if len(runs) > 1:
            reporter.write_comparison(runs, output / "model-comparison.json")
    except (OSError, ValueError, RamaLamaServerError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    for run, path in zip(runs, paths, strict=True):
        typer.echo(
            f"{run.model}: F1={run.metrics.f1:.4f}, "
            f"precision={run.metrics.precision:.4f}, "
            f"recall={run.metrics.recall:.4f} -> {path}"
        )


@qualification_app.command("golden-corpus")
def qualify_golden_corpus(
    corpus: Annotated[
        Path,
        typer.Option(
            "--corpus",
            exists=True,
            file_okay=False,
            readable=True,
            resolve_path=True,
            help="Versioned golden corpus root.",
        ),
    ] = cli_defaults.DEFAULT_GOLDEN_CORPUS,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            file_okay=False,
            help="Report root; defaults to .atlas/qualification/runs.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
) -> None:
    report = GoldenCorpusQualifier().run(corpus)
    report_json, report_md = QualificationRunReporter().write(
        report,
        corpus_root=corpus,
        project_root=Path.cwd(),
        output_root=output,
    )
    typer.echo(f"Qualification status    : {'passed' if report.passed else 'failed'}")
    typer.echo(f"Cases                   : {len(report.cases)}")
    typer.echo(f"Report JSON             : {report_json}")
    typer.echo(f"Report Markdown         : {report_md}")
    if not report.passed:
        raise typer.Exit(code=1)
