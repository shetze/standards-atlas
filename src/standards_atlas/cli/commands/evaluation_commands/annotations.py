"""Evaluation CLI command group extracted without behavioral changes."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Annotated

import typer

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
from standards_atlas.application.semantic_qualification.defaults import (
    STATEMENT_FUNCTION_PROMPT_VERSIONS,
)
from standards_atlas.application.semantic_qualification.proposals import (
    ProposalRunConfig,
)
from standards_atlas.application.services.evaluation import (
    AnnotationQualificationService,
    BaselineProposalGenerator,
    SemanticAnnotationReviewService,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.cli.composition import build_clause_reference_extraction_service
from standards_atlas.cli.runtime_managers import managed_mcp_server


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
    ] = cli_defaults.DEFAULT_WORKSPACE,
    output_root: Annotated[
        Path,
        typer.Option(
            "--output", file_okay=False, help="Persistent machine reference-analysis root."
        ),
    ] = Path(".atlas/data/evaluation/references"),
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
        result = build_clause_reference_extraction_service(workspace).run(
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
    ] = Path(".atlas/data/evaluation/references"),
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
    ] = Path(".atlas/data/evaluation/corpora"),
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
    ] = Path(".atlas/data/evaluation/corpora"),
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
        ".atlas/data/evaluation/corpora"
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
