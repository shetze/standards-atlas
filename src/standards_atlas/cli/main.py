"""Command-line interface for Standards Atlas."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas import __version__
from standards_atlas.adapters.alignment import AlignmentArtifactRepository
from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.adapters.atlasdata.metadata import AtlasDataLifecycleStatus
from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.adapters.docling import (
    DoclingArtifactRepository,
    DoclingJsonReader,
    DoclingNotInstalledError,
    DoclingPdfConverter,
    DocumentConversionError,
    ExtractionState,
)
from standards_atlas.adapters.doorstop import (
    AVAILABLE_DOORSTOP_TEMPLATES,
    DoorstopExportConfig,
    DoorstopExporter,
    DoorstopTemplateInstaller,
)
from standards_atlas.adapters.evaluation import EngineeringDocumentClauseProvider
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.llm import (
    CodexCliConfig,
    CodexCliLlmGateway,
    LlmConfig,
    OpenAICompatibleLlmGateway,
    RamaLamaServerError,
    RamaLamaServerManager,
)
from standards_atlas.adapters.markdown import MarkdownExporter
from standards_atlas.adapters.mcp import (
    CodexMcpConfig,
    McpCompatibilityProbe,
    McpServerConfig,
    McpServerProcessError,
    McpServerProcessManager,
    StreamableHttpJsonRpcTransport,
    run_mcp_server,
)
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
from standards_atlas.application.catalog import parse_page_list
from standards_atlas.application.model import AlignmentOptions, NormalizationOptions
from standards_atlas.application.normalization import NormalizationDataLossError
from standards_atlas.application.qualification import (
    GoldenCorpusQualifier,
    QualificationRunReporter,
)
from standards_atlas.application.services import (
    AlignmentReviewService,
    AlignmentService,
    AtlasDataLifecycleError,
    AtlasDataLifecycleService,
    AtlasDataOnboardingError,
    AtlasDataOnboardingService,
    ContentEnrichmentError,
    ContentEnrichmentService,
    DoclingPartSource,
    DocumentCompositionError,
    DocumentCompositionService,
    DocumentExportService,
    DocumentExtractionService,
    DocumentImportService,
    DocumentNormalizationService,
    DocumentSelectionError,
    DocumentSelectionService,
    ExtractionInspectionService,
    MarkdownExportService,
    ReferenceCandidateService,
)
from standards_atlas.application.services.atlasdata_toc_service import AtlasDataTocService
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
from standards_atlas.application.services.evaluation.defaults import (
    STATEMENT_FUNCTION_PROMPT_VERSIONS,
)
from standards_atlas.application.workflow import (
    EndToEndWorkflowService,
    WorkflowRunReporter,
    WorkflowStage,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.printers import print_document_summary
from standards_atlas.domain.model import DocumentKey


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


app = typer.Typer(
    name="standards-atlas",
    help="Semantic traceability platform for technical standards.",
    no_args_is_help=True,
)

inspect_app = typer.Typer(
    help="Inspect Standards Atlas artifacts for debugging and development.",
    no_args_is_help=True,
)

app.add_typer(inspect_app, name="inspect")

atlasdata_app = typer.Typer(
    help="Work with legacy AtlasData files.",
    no_args_is_help=True,
)

app.add_typer(atlasdata_app, name="atlasdata")

document_app = typer.Typer(
    help="Import, transform, and persist engineering documents.",
    no_args_is_help=True,
)

app.add_typer(document_app, name="document")

docling_app = typer.Typer(
    help="Convert and inspect private PDF extraction artefacts with Docling.",
    no_args_is_help=True,
)

app.add_typer(docling_app, name="docling")

normalize_app = typer.Typer(
    help="Normalize extracted documents before semantic alignment.",
    no_args_is_help=True,
)
app.add_typer(normalize_app, name="normalize")

reference_app = typer.Typer(
    help="Detect and inspect clause-reference candidates.",
    no_args_is_help=True,
)
app.add_typer(reference_app, name="references")

align_app = typer.Typer(
    help="Align reference candidates with the AtlasData document structure.",
    no_args_is_help=True,
)
app.add_typer(align_app, name="align")

document_export_app = typer.Typer(
    help="Export persisted engineering documents.",
    no_args_is_help=True,
)

document_app.add_typer(
    document_export_app,
    name="export",
)

catalog_app = typer.Typer(
    help="Validate and inspect standard catalogs.",
    no_args_is_help=True,
)
app.add_typer(catalog_app, name="catalog")

workflow_app = typer.Typer(
    help="Plan and run catalog-driven end-to-end workflows.",
    no_args_is_help=True,
)
app.add_typer(workflow_app, name="workflow")

doorstop_app = typer.Typer(
    help="Publish internal hierarchy-based Doorstop projects.",
    no_args_is_help=True,
)
app.add_typer(doorstop_app, name="doorstop")

llm_app = typer.Typer(
    help="Manage the project-owned local LLM server.",
    no_args_is_help=True,
)
app.add_typer(llm_app, name="llm")

mcp_app = typer.Typer(
    help="Expose read-only Standards Atlas data through Model Context Protocol.",
    no_args_is_help=True,
)
app.add_typer(mcp_app, name="mcp")

semantic_evaluation_app = typer.Typer(
    help="Benchmark prompts and models against versioned semantic gold datasets.",
    no_args_is_help=True,
)
app.add_typer(semantic_evaluation_app, name="semantic-evaluation")

evaluation_app = typer.Typer(
    help="Build local corpora and run reproducible evaluation matrices.",
    no_args_is_help=True,
)
app.add_typer(evaluation_app, name="evaluation")

qualification_app = typer.Typer(
    help="Execute reproducible qualification checks and persist evidence.",
    no_args_is_help=True,
)
app.add_typer(qualification_app, name="qualification")


def _managed_llm_server(config: Path) -> RamaLamaServerManager:
    return RamaLamaServerManager(LlmConfig.load(config))


@llm_app.command("start")
def start_llm_server(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="LLM YAML configuration."),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
) -> None:
    try:
        _managed_llm_server(config).start()
    except (OSError, ValueError, RamaLamaServerError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("RamaLama server started.")


@llm_app.command("stop")
def stop_llm_server(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="LLM YAML configuration."),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
) -> None:
    try:
        _managed_llm_server(config).stop()
    except (OSError, ValueError, RamaLamaServerError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("RamaLama server stopped.")


@llm_app.command("status")
def show_llm_server_status(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="LLM YAML configuration."),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
) -> None:
    try:
        status = _managed_llm_server(config).status()
    except (OSError, ValueError, RamaLamaServerError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("running" if status.running else "stopped")
    if status.detail:
        typer.echo(status.detail)


def _managed_mcp_server(config: Path) -> McpServerProcessManager:
    return McpServerProcessManager(McpServerConfig.load(config), config)


@mcp_app.command("start")
def start_mcp(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="MCP YAML configuration."),
    ] = cli_defaults.DEFAULT_MCP_CONFIG,
) -> None:
    """Start the MCP HTTP server as a managed background process."""
    try:
        _managed_mcp_server(config).start()
    except (OSError, RuntimeError, ValueError, McpServerProcessError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("MCP server started.")


@mcp_app.command("stop")
def stop_mcp(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="MCP YAML configuration."),
    ] = cli_defaults.DEFAULT_MCP_CONFIG,
) -> None:
    """Stop the managed MCP background process."""
    try:
        _managed_mcp_server(config).stop()
    except (OSError, RuntimeError, ValueError, McpServerProcessError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("MCP server stopped.")


@mcp_app.command("status")
def show_mcp_status(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="MCP YAML configuration."),
    ] = cli_defaults.DEFAULT_MCP_CONFIG,
) -> None:
    """Show process and endpoint status for the managed MCP server."""
    try:
        status = _managed_mcp_server(config).status()
    except (OSError, RuntimeError, ValueError, McpServerProcessError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("running" if status.running else "stopped")
    if status.pid is not None:
        typer.echo(f"pid: {status.pid}")
    if status.detail:
        typer.echo(status.detail)


@mcp_app.command("serve")
def serve_mcp(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="MCP YAML configuration."),
    ] = cli_defaults.DEFAULT_MCP_CONFIG,
) -> None:
    """Run the read-only MCP server in the foreground."""
    try:
        run_mcp_server(McpServerConfig.load(config))
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


@mcp_app.command("probe")
def probe_mcp(
    url: Annotated[str, typer.Option("--url", help="Streamable HTTP MCP endpoint.")],
    token_environment_variable: Annotated[
        str,
        typer.Option(
            "--token-env",
            help="Environment variable containing the bearer token.",
        ),
    ] = cli_defaults.DEFAULT_MCP_TOKEN_ENVIRONMENT_VARIABLE,
    timeout_seconds: Annotated[
        float,
        typer.Option("--timeout", min=0.1, help="HTTP timeout in seconds."),
    ] = cli_defaults.DEFAULT_MCP_TIMEOUT_SECONDS,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional JSON report path."),
    ] = cli_defaults.DEFAULT_NONE,
) -> None:
    """Run an interoperable MCP handshake and read-only contract probe."""
    import os

    token = os.environ.get(token_environment_variable)
    transport = StreamableHttpJsonRpcTransport(
        url,
        bearer_token=token,
        timeout_seconds=timeout_seconds,
    )
    try:
        report = McpCompatibilityProbe(transport).run()
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    payload = report.as_dict()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{rendered}\n", encoding="utf-8")
    typer.echo(rendered)
    if not report.passed:
        raise typer.Exit(code=1)


@mcp_app.command("codex-config")
def render_codex_mcp_config(
    url: Annotated[str, typer.Option("--url", help="Streamable HTTP MCP endpoint.")],
    server_name: Annotated[
        str,
        typer.Option("--name", help="Codex MCP server name."),
    ] = cli_defaults.DEFAULT_MCP_SERVER_NAME,
    token_environment_variable: Annotated[
        str,
        typer.Option(
            "--token-env",
            help="Environment variable containing the bearer token.",
        ),
    ] = cli_defaults.DEFAULT_MCP_TOKEN_ENVIRONMENT_VARIABLE,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional config fragment path."),
    ] = cli_defaults.DEFAULT_NONE,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace an existing output file."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Render a secure Codex Streamable HTTP MCP configuration fragment."""
    try:
        config = CodexMcpConfig(
            url=url,
            server_name=server_name,
            bearer_token_env_var=token_environment_variable,
        )
        if output is not None:
            config.write(output, overwrite=overwrite)
    except (FileExistsError, OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(config.render_toml())
    typer.echo("Equivalent registration command:", err=True)
    typer.echo(" ".join(config.codex_add_command()), err=True)


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
            mcp_manager = _managed_mcp_server(mcp_config)
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
                            mcp_manager = _managed_mcp_server(mcp_config)
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


@catalog_app.command("validate")
def validate_catalog(
    catalog: Annotated[Path, typer.Argument(help="YAML standard catalog.")],
) -> None:
    model = YamlStandardCatalogReader().read(catalog)
    typer.echo(f"Catalog version        : {model.version}")
    typer.echo(f"Knowledge domains      : {len(model.knowledge_domains)}")
    typer.echo(f"Industry sectors       : {len(model.industry_sectors)}")
    typer.echo(f"Standard families      : {len(model.families)}")
    typer.echo(f"Profiles               : {len(model.profiles)}")
    typer.echo(f"Doorstop hierarchies   : {len(model.doorstop_hierarchies)}")


@workflow_app.command("plan")
def plan_workflow(
    catalog: Annotated[Path, typer.Option("--catalog", help="YAML standard catalog.")],
    family: Annotated[
        list[str] | None, typer.Option("--family", help="Family key; repeat as needed.")
    ] = cli_defaults.DEFAULT_NONE,
    profile: Annotated[
        str | None, typer.Option("--profile", help="Catalog profile key.")
    ] = cli_defaults.DEFAULT_NONE,
    all_families: Annotated[
        bool, typer.Option("--all", help="Plan all catalog families.")
    ] = cli_defaults.DEFAULT_FALSE,
    hierarchy: Annotated[
        str | None, typer.Option("--hierarchy", help="Doorstop hierarchy key.")
    ] = cli_defaults.DEFAULT_NONE,
    force: Annotated[
        bool,
        typer.Option("--force", help="Plan regeneration using only supported replacement options."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    model = YamlStandardCatalogReader().read(catalog)
    keys = (
        model.doorstop_hierarchy(hierarchy).families
        if hierarchy is not None
        else _select_catalog_families(model, tuple(family or ()), profile, all_families)
    )
    plan = EndToEndWorkflowService().plan(
        model,
        family_keys=keys,
        catalog_root=Path.cwd(),
        force=force,
        hierarchy_key=hierarchy,
    )
    for step in plan.steps:
        gate = " [manual review gate]" if step.manual_gate else ""
        typer.echo(f"{step.family:20} {step.stage.value:12} {' '.join(step.command)}{gate}")


@workflow_app.command("run")
def run_workflow(
    catalog: Annotated[Path, typer.Option("--catalog", help="YAML standard catalog.")],
    family: Annotated[
        list[str] | None, typer.Option("--family", help="Family key; repeat as needed.")
    ] = cli_defaults.DEFAULT_NONE,
    profile: Annotated[
        str | None, typer.Option("--profile", help="Catalog profile key.")
    ] = cli_defaults.DEFAULT_NONE,
    all_families: Annotated[
        bool, typer.Option("--all", help="Run all catalog families.")
    ] = cli_defaults.DEFAULT_FALSE,
    hierarchy: Annotated[
        str | None, typer.Option("--hierarchy", help="Doorstop hierarchy key.")
    ] = cli_defaults.DEFAULT_NONE,
    continue_after_review: Annotated[
        bool,
        typer.Option(
            "--continue-after-review",
            help="Continue only when reviewed alignments already exist.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Regenerate all reproducible artifacts, including Docling output.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Regenerate derived artifacts; combine with --keep to reuse selected stages.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    keep: Annotated[
        list[WorkflowStage] | None,
        typer.Option(
            "--keep",
            help="Reuse an existing stage while overwriting later artifacts; repeat as needed.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
) -> None:
    if force and overwrite:
        raise typer.BadParameter("--force and --overwrite are mutually exclusive")
    if keep and not overwrite:
        raise typer.BadParameter("--keep requires --overwrite")

    model = YamlStandardCatalogReader().read(catalog)
    keys = (
        model.doorstop_hierarchy(hierarchy).families
        if hierarchy is not None
        else _select_catalog_families(model, tuple(family or ()), profile, all_families)
    )
    plan = EndToEndWorkflowService().plan(
        model,
        family_keys=keys,
        catalog_root=Path.cwd(),
        force=force or overwrite,
        keep_stages=tuple(keep or ()),
        hierarchy_key=hierarchy,
    )
    result = EndToEndWorkflowService().execute(
        plan, project_root=Path.cwd(), continue_after_review=continue_after_review
    )
    if result.completed:
        report_json, report_md = WorkflowRunReporter().write(
            plan,
            result,
            project_root=Path.cwd(),
            catalog_path=catalog,
            hierarchy_key=hierarchy,
        )
        typer.echo(f"Workflow completed      : {len(result.executed_steps)} steps")
        typer.echo(f"Run report JSON         : {report_json}")
        typer.echo(f"Run report Markdown     : {report_md}")
        return

    typer.echo(f"Workflow paused         : {len(result.executed_steps)} steps executed")
    if result.blocked_documents:
        typer.echo("Review required for     : " + ", ".join(result.blocked_documents))
    if result.blocked_families:
        typer.echo("AtlasData review for    : " + ", ".join(result.blocked_families))
    typer.echo("Continue after completing the reviews with --continue-after-review.")


def _select_catalog_families(
    model,
    families: tuple[str, ...],
    profile: str | None,
    all_families: bool,
) -> tuple[str, ...]:
    selected = sum((bool(families), profile is not None, all_families))
    if selected != 1:
        raise typer.BadParameter("select exactly one of --family, --profile, or --all")
    if families:
        for key in families:
            model.family(key)
        return families
    if profile is not None:
        return model.profile(profile).families
    return tuple(family.key for family in model.families)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", "-v", help="Show the Standards Atlas version and exit."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Standards Atlas command-line entry point."""
    if version:
        typer.echo(f"standards-atlas {__version__}")
        raise typer.Exit()


@app.command()
def info() -> None:
    """Show basic project information."""
    typer.echo("Standards Atlas")
    typer.echo("Semantic traceability platform for technical standards.")


@inspect_app.command("data")
def inspect_data(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            resolve_path=True,
            help="Atlas data file to inspect.",
        ),
    ],
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-V", help="Show parsed clause details."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Inspect a legacy Atlas data file through the canonical domain model."""
    reader = AtlasDataImporter()
    service = DocumentImportService(reader)
    document = service.import_document(file)
    print_document_summary(document, source_file=file, verbose=verbose)


@atlasdata_app.command("onboard-docling")
def onboard_docling(
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            resolve_path=True,
            help="Docling document.json used to discover public clause structure.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Argument(help="AtlasData file to create."),
    ],
    standard_name: Annotated[
        str,
        typer.Option("--name", help="Official standard name used in references."),
    ],
    year: Annotated[
        int,
        typer.Option("--year", help="Publication year."),
    ],
    digits: Annotated[
        int,
        typer.Option("--digits", help="AtlasData numeric identifier width."),
    ] = cli_defaults.DEFAULT_ATLASDATA_DIGITS,
    parent: Annotated[
        str | None,
        typer.Option("--parent", help="Optional AtlasData parent key."),
    ] = cli_defaults.DEFAULT_NONE,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace an existing output file."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Create an AtlasData skeleton from numbered Docling headings."""
    try:
        result = AtlasDataOnboardingService().generate(
            source,
            output,
            standard_name=standard_name,
            year=year,
            digits=digits,
            parent=parent,
            overwrite=overwrite,
        )
    except (AtlasDataOnboardingError, OSError, ValueError, json.JSONDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    term_count = sum(clause.type_marker == "t" for clause in result.clauses)
    typer.echo(f"Document source       : {source}")
    typer.echo(f"Standard              : {result.standard_name}")
    typer.echo(f"Publication year      : {result.year}")
    typer.echo(f"Clauses discovered    : {len(result.clauses)}")
    typer.echo(f"Terms discovered      : {term_count}")
    typer.echo(f"AtlasData file        : {result.output}")


@atlasdata_app.command("onboard-docling-parts")
def onboard_docling_parts(
    output: Annotated[Path, typer.Argument(help="AtlasData file to create.")],
    parts: Annotated[
        list[str],
        typer.Option(
            "--part",
            help="Explicit PART=PATH association. Repeat once per standard part.",
        ),
    ],
    standard_name: Annotated[
        str, typer.Option("--name", help="Official standard family name used in references.")
    ],
    year: Annotated[int, typer.Option("--year", help="Publication year.")],
    digits: Annotated[
        int, typer.Option("--digits", help="AtlasData numeric identifier width.")
    ] = cli_defaults.DEFAULT_ATLASDATA_DIGITS,
    parent: Annotated[
        str | None, typer.Option("--parent", help="Optional AtlasData parent key.")
    ] = cli_defaults.DEFAULT_NONE,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing output file.")
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Create one AtlasData file from explicitly assigned Docling part documents."""
    try:
        sources = tuple(DoclingPartSource.parse(value) for value in parts)
        result = AtlasDataOnboardingService().generate_parts(
            sources,
            output,
            standard_name=standard_name,
            year=year,
            digits=digits,
            parent=parent,
            overwrite=overwrite,
        )
    except (AtlasDataOnboardingError, OSError, ValueError, json.JSONDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    term_count = sum(clause.type_marker == "t" for clause in result.clauses)
    annex_count = sum(
        len(
            {
                clause.reference.split(".")[0]
                for clause in part.clauses
                if clause.reference[0].isalpha()
            }
        )
        for part in result.parts
    )
    typer.echo(f"Standard              : {result.standard_name}")
    typer.echo(f"Publication year      : {result.year}")
    typer.echo(f"Parts discovered      : {len(result.parts)}")
    for part in result.parts:
        typer.echo(f"Part {part.part:<17}: {part.source} ({len(part.clauses)} clauses)")
    typer.echo(f"Clauses discovered    : {len(result.clauses)}")
    typer.echo(f"Terms discovered      : {term_count}")
    typer.echo(f"Annexes discovered    : {annex_count}")
    typer.echo(f"AtlasData file        : {result.output}")


@atlasdata_app.command("set-status")
def set_atlasdata_status(
    file: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, writable=True, resolve_path=True),
    ],
    status: Annotated[
        AtlasDataLifecycleStatus,
        typer.Argument(help="Target lifecycle status: reviewed or published."),
    ],
) -> None:
    """Advance an AtlasData baseline through its review lifecycle."""
    try:
        result = AtlasDataLifecycleService().transition(file, status)
    except (AtlasDataLifecycleError, OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"AtlasData file        : {result.path}")
    typer.echo(f"Previous status      : {result.previous.value}")
    typer.echo(f"Lifecycle status     : {result.current.value}")


@atlasdata_app.command("generate-toc")
def generate_toc(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            resolve_path=True,
            help="AtlasData file to update.",
        ),
    ],
    write: Annotated[
        bool,
        typer.Option("--write", help="Write changes to the file."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Generate the TOC data section for an AtlasData file."""
    service = AtlasDataTocService()
    result = service.update_toc(file, write=write)

    typer.echo(f"File                  : {result.source.name}")
    typer.echo(f"Generated TOC records : {result.generated_toc_records}")
    typer.echo(f"Preserved headings    : {result.preserved_toc_headings}")
    typer.echo(f"Preserved TEXT records: {result.preserved_public_text_records}")
    typer.echo(f"Removed records       : {result.removed_records}")
    typer.echo(f"Changed               : {result.changed}")

    if write:
        if result.backup:
            typer.echo(f"Backup                : {result.backup.name}")
        else:
            typer.echo("Backup                : not created; file unchanged")
    else:
        typer.echo()
        typer.echo("Dry run only. Use --write to update the file.")


@document_app.command("import")
def import_document(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            resolve_path=True,
            help="Document source file to import.",
        ),
    ],
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            "-w",
            help="Standards Atlas workspace directory.",
        ),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Import an engineering document into the local Standards Atlas workspace."""
    importer = AtlasDataImporter()
    repository = FileSystemEngineeringDocumentRepository(workspace=workspace)

    service = DocumentImportService(
        importer=importer,
        repository=repository,
    )

    document = service.import_document(file)

    typer.echo(f"Imported document     : {document.title}")
    typer.echo(f"Key                   : {document.key.value}")
    typer.echo(f"Clauses               : {len(document.clauses)}")
    typer.echo(f"Workspace             : {workspace}")


@document_app.command("derive")
def derive_document_view(
    source_key: Annotated[str, typer.Argument(help="Key of the persisted master document.")],
    target_key: Annotated[str, typer.Option("--key", help="Key for the derived document view.")],
    standard_name: Annotated[
        str,
        typer.Option("--standard", help="Exact StandardReference.standard value to select."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Create a persisted document view matching one physical source document."""
    service = DocumentSelectionService(workspace)
    try:
        document = service.derive_by_standard_name(source_key, target_key, standard_name)
    except DocumentSelectionError as error:
        raise typer.BadParameter(str(error)) from error

    typer.echo(f"Source document       : {source_key}")
    typer.echo(f"Selected standard     : {standard_name}")
    typer.echo(f"Derived key           : {document.key.value}")
    typer.echo(f"Clauses               : {len(document.clauses)}")
    typer.echo(f"Persisted document    : {workspace / 'documents' / (target_key + '.json')}")


@document_app.command("derive-part")
def derive_document_part(
    source_key: Annotated[str, typer.Argument(help="Key of the persisted master document.")],
    part: Annotated[str, typer.Argument(help="AtlasData volume/part identifier.")],
    target_key: Annotated[str, typer.Option("--key", help="Key for the derived document view.")],
    title: Annotated[
        str | None, typer.Option("--title", help="Title of the derived part.")
    ] = cli_defaults.DEFAULT_NONE,
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Create a persisted document view for one AtlasData volume or standard part."""
    service = DocumentSelectionService(workspace)
    try:
        document = service.derive_by_volume(source_key, target_key, part, title)
    except DocumentSelectionError as error:
        raise typer.BadParameter(str(error)) from error

    typer.echo(f"Source document       : {source_key}")
    typer.echo(f"Selected part         : {part}")
    typer.echo(f"Derived key           : {document.key.value}")
    typer.echo(f"Clauses               : {len(document.clauses)}")
    typer.echo(f"Persisted document    : {workspace / 'documents' / (target_key + '.json')}")


@document_app.command("compose-family")
def compose_family_document(
    family_key: Annotated[str, typer.Argument(help="Key of the persisted family document.")],
    part: Annotated[
        list[str] | None,
        typer.Option("--part", help="Enriched part key; repeat for every part."),
    ] = cli_defaults.DEFAULT_NONE,
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Merge enriched part documents back into their logical family document."""
    part_keys = tuple(part or ())
    if not part_keys:
        raise typer.BadParameter("At least one --part document key is required.")
    try:
        document = DocumentCompositionService(workspace).compose(family_key, part_keys)
    except (DocumentCompositionError, FileNotFoundError) as error:
        raise typer.BadParameter(str(error)) from error

    enriched = sum(bool(clause.content) for clause in document.clauses)
    typer.echo(f"Family document       : {document.key.value}")
    typer.echo(f"Part documents        : {', '.join(part_keys)}")
    typer.echo(f"Clauses               : {len(document.clauses)}")
    typer.echo(f"Clauses with content  : {enriched}")


@document_app.command("enrich-content")
def enrich_document_content(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the aligned EngineeringDocument to enrich."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    automatic_alignment: Annotated[
        bool,
        typer.Option(
            "--automatic-alignment",
            help="Use alignment.json even when reviewed.json exists.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    allow_unresolved: Annotated[
        bool,
        typer.Option(
            "--allow-unresolved",
            help="Keep unresolved clauses unchanged instead of aborting.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Populate clause ContentBlocks from aligned normalized document ranges."""
    try:
        result = ContentEnrichmentService(workspace).enrich(
            document_key,
            prefer_reviewed=not automatic_alignment,
            allow_unresolved=allow_unresolved,
        )
    except (ContentEnrichmentError, OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    stats = result.statistics
    typer.echo(f"Document              : {result.document.key.value}")
    typer.echo(f"Clauses               : {stats.clauses_total}")
    typer.echo(f"Clauses enriched      : {stats.clauses_enriched}")
    typer.echo(f"Clauses empty         : {stats.clauses_empty}")
    typer.echo(f"Content blocks        : {stats.content_blocks}")
    typer.echo(f"Normalized items      : {stats.normalized_items_consumed}")
    typer.echo(
        "Alignment source      : "
        + ("reviewed.json" if stats.used_reviewed_alignment else "alignment.json")
    )
    typer.echo(f"Persisted document    : {workspace / 'documents' / (document_key + '.json')}")


@document_export_app.command("markdown")
def export_document_to_markdown(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the persisted EngineeringDocument or standard family."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    target: Annotated[
        Path | None,
        typer.Option(
            "--target",
            "-t",
            help="Common target directory. Defaults to local/exports/markdown/<document-key>.",
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = cli_defaults.DEFAULT_NONE,
    replace_existing: Annotated[
        bool,
        typer.Option("--replace/--no-replace", help="Replace existing Markdown files."),
    ] = cli_defaults.DEFAULT_TRUE,
) -> None:
    """Export one standard family to one Markdown file per physical part."""
    export_target = target if target is not None else Path("local/exports/markdown") / document_key
    service = MarkdownExportService(MarkdownExporter(), workspace=workspace)
    try:
        result = service.export(
            document_key=document_key,
            target_directory=export_target,
            replace_existing=replace_existing,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Document key          : {result.document_key}")
    typer.echo(f"Clauses exported      : {result.clauses_exported}")
    typer.echo(f"Markdown files        : {len(result.generated_files)}")
    for generated in result.generated_files:
        typer.echo(f"  {generated}")


@document_export_app.command("doorstop")
def export_document_to_doorstop(
    document_key: Annotated[
        str,
        typer.Argument(
            help="Key of the persisted EngineeringDocument to export.",
        ),
    ],
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            "-w",
            help="Standards Atlas workspace directory.",
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    target: Annotated[
        Path | None,
        typer.Option(
            "--target",
            "-t",
            help=(
                "Target directory for the Doorstop document. "
                "Defaults to <workspace>/doorstop/<document-key>."
            ),
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = cli_defaults.DEFAULT_NONE,
    prefix: Annotated[
        str | None,
        typer.Option(
            "--prefix",
            help="Doorstop document prefix.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
    digits: Annotated[
        int,
        typer.Option(
            "--digits",
            min=1,
            help="Number of digits used for Doorstop item identifiers.",
        ),
    ] = cli_defaults.DEFAULT_ATLASDATA_DIGITS,
    separator: Annotated[
        str,
        typer.Option(
            "--separator",
            help="Separator between Doorstop prefix and numeric identifier.",
        ),
    ] = cli_defaults.DEFAULT_DOORSTOP_SEPARATOR,
    parent: Annotated[
        str | None,
        typer.Option(
            "--parent",
            help="Doorstop parent document prefix derived from the catalog hierarchy.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
    validate: Annotated[
        bool,
        typer.Option(
            "--validate/--no-validate",
            help="Validate the generated Doorstop document after export.",
        ),
    ] = cli_defaults.DEFAULT_TRUE,
    replace_existing: Annotated[
        bool,
        typer.Option(
            "--replace/--no-replace",
            help="Replace an existing Doorstop export directory.",
        ),
    ] = cli_defaults.DEFAULT_TRUE,
    initialize_git: Annotated[
        bool,
        typer.Option(
            "--init-git/--no-init-git",
            help="Initialize the Doorstop target as a Git repository.",
        ),
    ] = cli_defaults.DEFAULT_TRUE,
) -> None:
    """Export a persisted EngineeringDocument as a Doorstop document."""
    repository = FileSystemEngineeringDocumentRepository(
        workspace=workspace,
    )

    key = DocumentKey(value=document_key)

    if not repository.exists(key):
        typer.echo(
            f"No persisted document found for key: {document_key}",
            err=True,
        )
        typer.echo(
            "Import the document first with:",
            err=True,
        )
        typer.echo(
            f"  standards-atlas document import <source> --workspace {workspace}",
            err=True,
        )
        raise typer.Exit(code=1)

    document = repository.load(key)

    export_target = target if target is not None else workspace / "doorstop" / document.key.value

    config = DoorstopExportConfig(
        workspace=workspace / "doorstop",
        prefix=prefix,
        digits=digits,
        separator=separator,
        parent=parent,
        replace_existing=replace_existing,
        validate_after_export=validate,
        initialize_git_repository=initialize_git,
    )

    exporter = DoorstopExporter(config=config)
    service = DocumentExportService(exporter=exporter)

    try:
        generated_path = service.export_document(
            document=document,
            target=export_target,
        )
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except RuntimeError as exc:
        typer.echo("Doorstop export failed.", err=True)
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc

    typer.echo(f"Exported document     : {document.title}")
    typer.echo(f"Document key          : {document.key.value}")
    typer.echo(f"Clauses exported      : {len(document.clauses)}")
    typer.echo(f"Doorstop target       : {generated_path}")
    typer.echo(f"Validation enabled    : {validate}")


@doorstop_app.command("publish")
def publish_doorstop_hierarchy(
    hierarchy_key: Annotated[str, typer.Argument(help="Doorstop hierarchy key.")],
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Internal Standards Atlas workspace.")
    ] = cli_defaults.DEFAULT_WORKSPACE,
    local_root: Annotated[
        Path, typer.Option("--local-root", help="Root for local consumable outputs.")
    ] = cli_defaults.DEFAULT_LOCAL_ROOT,
    replace_existing: Annotated[
        bool, typer.Option("--replace/--no-replace", help="Replace published output.")
    ] = cli_defaults.DEFAULT_TRUE,
    template: Annotated[
        str,
        typer.Option(
            "--template",
            help="Packaged Standards Atlas Doorstop template.",
        ),
    ] = cli_defaults.DEFAULT_DOORSTOP_TEMPLATE,
) -> None:
    """Publish one internal Doorstop hierarchy for local consumption."""
    source = workspace / "doorstop" / hierarchy_key
    target = local_root / "exports" / "doorstop" / hierarchy_key
    if not source.is_dir():
        typer.echo(f"Doorstop hierarchy not found: {source}", err=True)
        raise typer.Exit(code=2)
    if template not in AVAILABLE_DOORSTOP_TEMPLATES:
        choices = ", ".join(AVAILABLE_DOORSTOP_TEMPLATES)
        typer.echo(f"Unknown Doorstop template {template!r}; choose one of: {choices}", err=True)
        raise typer.Exit(code=2)
    if target.exists():
        if not replace_existing:
            typer.echo(f"Published output already exists: {target}", err=True)
            raise typer.Exit(code=2)
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        installed_template = DoorstopTemplateInstaller().install(source, template)
        subprocess.run(
            ("doorstop", "publish", "--template", "doorstop", "all", str(target.resolve())),
            cwd=source,
            check=True,
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        typer.echo(f"Doorstop publish failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    typer.echo(f"Doorstop hierarchy     : {hierarchy_key}")
    typer.echo(f"Published output      : {target}")
    typer.echo(f"Template              : {template}")
    typer.echo(f"Installed template    : {installed_template}")


@docling_app.command("convert")
def convert_pdf_with_docling(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            resolve_path=True,
            help="PDF file to convert.",
        ),
    ],
    document_key: Annotated[
        str,
        typer.Option("--document", "-d", help="Key used below .atlas/docling/."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace an existing native Docling document."),
    ] = cli_defaults.DEFAULT_FALSE,
    llm_config: Annotated[
        Path,
        typer.Option(
            "--llm-config",
            exists=True,
            readable=True,
            help="Managed LLM configuration used to release the GPU during conversion.",
        ),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
) -> None:
    """Convert a PDF and persist native Docling JSON below the private workspace."""
    repository = DoclingArtifactRepository(workspace)
    converter = DoclingPdfConverter()
    service = DocumentExtractionService(converter, DoclingJsonReader())

    try:
        state = repository.extraction_state(document_key, file)
        if state is ExtractionState.CURRENT and not overwrite:
            typer.echo("Existing extraction matches the source PDF.")
            typer.echo(f"Docling document      : {repository.document_path(document_key)}")
            return
        if state is ExtractionState.STALE and not overwrite:
            typer.echo(
                "The source PDF has changed since the last conversion. "
                "Use --overwrite to update the extraction.",
                err=True,
            )
            raise typer.Exit(code=3)
        if state is ExtractionState.INCOMPLETE and not overwrite:
            typer.echo(
                "The persisted extraction is incomplete. Use --overwrite to repair it.",
                err=True,
            )
            raise typer.Exit(code=3)

        target = repository.document_path(document_key)
        server = _managed_llm_server(llm_config)
        with server.stopped_for_exclusive_accelerator():
            generated = service.convert(file, target, overwrite=overwrite)
        repository.save_metadata(document_key, converter.conversion_metadata(file))
    except (
        DoclingNotInstalledError,
        DocumentConversionError,
        FileExistsError,
        RamaLamaServerError,
        ValueError,
    ) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Converted PDF         : {file}")
    typer.echo(f"Document key          : {document_key}")
    typer.echo(f"Docling document      : {generated}")
    typer.echo(f"Conversion metadata   : {repository.metadata_path(document_key)}")


@docling_app.command("inspect")
def inspect_docling_document(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of a persisted Docling document."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Inspect extraction coverage without loading the Docling runtime."""
    repository = DoclingArtifactRepository(workspace)
    try:
        source = repository.document_path(document_key)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    if not source.exists():
        typer.echo(f"No Docling document found for key: {document_key}", err=True)
        raise typer.Exit(code=1)

    extracted = DoclingJsonReader().read(source)
    statistics = ExtractionInspectionService().inspect(extracted)
    typer.echo(f"Document source       : {extracted.source_id}")
    typer.echo(f"Pages                 : {statistics.page_count}")
    typer.echo(f"Extracted items       : {statistics.item_count}")
    typer.echo(f"Items with page data  : {statistics.items_with_page_evidence}")
    typer.echo(f"Items without page data: {statistics.items_without_page_evidence}")
    typer.echo(f"Unknown items         : {statistics.unknown_item_count}")
    for item_type, count in statistics.counts_by_type.items():
        typer.echo(f"{item_type.capitalize():22}: {count}")
    if statistics.unknown_labels:
        typer.echo(f"Unknown labels        : {', '.join(statistics.unknown_labels)}")


def _parse_page_range(value: str) -> tuple[int, int | None]:
    try:
        start_text, end_text = value.split(":", maxsplit=1)
        start = int(start_text)
        end = int(end_text) if end_text else None
    except ValueError as exc:
        raise ValueError(f"Invalid page range {value!r}; expected START:END or START:") from exc
    if start < 1 or (end is not None and end < start):
        raise ValueError(f"Invalid page range {value!r}")
    return start, end


@normalize_app.command("run")
def normalize_extracted_document(
    document_key: Annotated[str, typer.Argument(help="Key of a persisted Docling document.")],
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
    ] = cli_defaults.DEFAULT_WORKSPACE,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing normalized document.")
    ] = cli_defaults.DEFAULT_FALSE,
    page_range: Annotated[
        list[str] | None,
        typer.Option(
            "--page-range",
            help="Inclusive positive one-based page range START:END; repeat for multiple ranges.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
    exclude_page_range: Annotated[
        list[str] | None,
        typer.Option(
            "--exclude-page-range",
            help="Inclusive one-based page range to exclude; repeat for multiple ranges.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
    page_list: Annotated[
        str | None,
        typer.Option(
            "--page-list",
            help="Positive comma-separated pages and ranges, for example 1,3,5,11-13,15.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
) -> None:
    """Normalize an extracted document and persist the result below .atlas."""
    repository = NormalizationArtifactRepository(workspace)
    target = repository.document_path(document_key)
    if target.exists() and not overwrite:
        typer.echo("A normalized document already exists. Use --overwrite to replace it.", err=True)
        raise typer.Exit(code=3)
    try:
        page_ranges = tuple(_parse_page_range(value) for value in (page_range or ()))
        excluded_ranges = tuple(_parse_page_range(value) for value in (exclude_page_range or ()))
        selected_pages = parse_page_list(page_list) if page_list else ()
        result = DocumentNormalizationService(workspace=workspace).normalize(
            document_key,
            options=NormalizationOptions(
                page_ranges=page_ranges,
                exclude_page_ranges=excluded_ranges,
                page_list=selected_pages,
            ),
        )
    except (NormalizationDataLossError, OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source             : {result.source_id}")
    typer.echo(f"Input items                 : {stats.input_items}")
    typer.echo(f"Output items                : {stats.output_items}")
    typer.echo(f"Headers suppressed          : {stats.headers_suppressed}")
    typer.echo(f"Footers suppressed          : {stats.footers_suppressed}")
    typer.echo(f"Page numbers suppressed     : {stats.page_numbers_suppressed}")
    typer.echo(f"Hyphenations repaired       : {stats.hyphenations_repaired}")
    typer.echo(f"Text fragments merged       : {stats.text_fragments_merged}")
    typer.echo(f"Lists normalized            : {stats.lists_normalized}")
    typer.echo(f"Code blocks                 : {stats.code_blocks}")
    typer.echo(f"Active source items         : {stats.active_source_items}")
    typer.echo(f"Suppressed source items     : {stats.suppressed_source_items}")
    typer.echo(f"Unaccounted source items    : {stats.unaccounted_source_items}")
    typer.echo(f"Duplicate source items      : {stats.duplicate_source_items}")
    typer.echo(f"Source pages                : {stats.source_pages}")
    options = result.metadata.options
    if options.page_ranges:
        rendered_ranges = ", ".join(
            f"{start}-{end if end is not None else 'end'}" for start, end in options.page_ranges
        )
        typer.echo(f"Selected page ranges        : {rendered_ranges}")
    if options.page_list:
        typer.echo(
            "Selected page list          : " + ",".join(str(page) for page in options.page_list)
        )
    if options.exclude_page_ranges:
        rendered_exclusions = ", ".join(
            f"{start}-{end if end is not None else 'end'}"
            for start, end in options.exclude_page_ranges
        )
        typer.echo(f"Excluded page ranges        : {rendered_exclusions}")
    if options.page_ranges or options.page_list or options.exclude_page_ranges:
        typer.echo(f"Pages included              : {stats.selected_pages}")
        typer.echo(f"Pages excluded              : {stats.excluded_pages}")
    typer.echo(f"Normalized document         : {target}")


@normalize_app.command("inspect")
def inspect_normalized_document(
    document_key: Annotated[str, typer.Argument(help="Key of a normalized document.")],
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Inspect normalization statistics and diagnostics."""
    try:
        result = NormalizationArtifactRepository(workspace).load(document_key)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source             : {result.source_id}")
    typer.echo(f"Input items                 : {stats.input_items}")
    typer.echo(f"Output items                : {stats.output_items}")
    typer.echo(f"Suppressed items            : {len(result.suppressed_items)}")
    typer.echo(f"Normalization issues        : {len(result.issues)}")
    typer.echo(f"Code blocks                 : {stats.code_blocks}")
    typer.echo(f"Active source items         : {stats.active_source_items}")
    typer.echo(f"Suppressed source items     : {stats.suppressed_source_items}")
    typer.echo(f"Unaccounted source items    : {stats.unaccounted_source_items}")
    typer.echo(f"Duplicate source items      : {stats.duplicate_source_items}")


@reference_app.command("detect")
def detect_reference_candidates(
    document_key: Annotated[
        str,
        typer.Argument(
            help="Key of the normalized and engineering document.",
        ),
    ],
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Detect clause-reference candidates and validate them against AtlasData structure."""
    try:
        result = ReferenceCandidateService(workspace).detect(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source       : {result.source_id}")
    typer.echo(f"Input items           : {stats.input_items}")
    typer.echo(f"Candidates            : {stats.candidates}")
    typer.echo(f"Expected              : {stats.expected_candidates}")
    typer.echo(f"Unexpected            : {stats.unexpected_candidates}")
    typer.echo(f"Ambiguous             : {stats.ambiguous_candidates}")
    typer.echo(f"Exact matches         : {stats.exact_matches}")
    typer.echo(f"Normalized matches    : {stats.normalized_matches}")
    typer.echo(f"Annex matches         : {stats.annex_matches}")
    repository = ReferenceCandidateRepository(workspace)
    document_path = repository.document_path(document_key)
    typer.echo(f"Candidate document    : {document_path}")


@reference_app.command("inspect")
def inspect_reference_candidates(
    document_key: Annotated[str, typer.Argument(help="Key of a persisted candidate document.")],
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
    ] = cli_defaults.DEFAULT_WORKSPACE,
    show_unexpected: Annotated[
        bool, typer.Option("--show-unexpected", help="Print unexpected and ambiguous candidates.")
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Inspect persisted clause-reference candidates."""
    try:
        result = ReferenceCandidateService(workspace).load(document_key)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source       : {result.source_id}")
    typer.echo(f"Candidates            : {stats.candidates}")
    typer.echo(f"Expected              : {stats.expected_candidates}")
    typer.echo(f"Unexpected            : {stats.unexpected_candidates}")
    typer.echo(f"Ambiguous             : {stats.ambiguous_candidates}")
    typer.echo(f"Issues                : {len(result.issues)}")
    if show_unexpected:
        for candidate in result.candidates:
            if candidate.status.value != "expected":
                typer.echo(
                    f"{candidate.sequence_number:5} {candidate.status.value:10} "
                    f"{candidate.normalized_reference:12} "
                    f"{candidate.title_remainder or candidate.following_label or ''}"
                )


@align_app.command("run")
def run_alignment(
    document_key: Annotated[
        str,
        typer.Argument(
            help="Key shared by the engineering, normalized and candidate documents.",
        ),
    ],
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            "-w",
            help="Standards Atlas workspace directory.",
        ),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Replace an existing alignment result.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Align reference candidates monotonically with AtlasData clauses."""
    repository = AlignmentArtifactRepository(workspace)
    target = repository.document_path(document_key)
    if target.exists() and not overwrite:
        typer.echo(
            "An alignment result already exists. Use --overwrite to replace it.",
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        result = AlignmentService(workspace).run(
            document_key,
            AlignmentOptions(),
        )
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source       : {result.source_id}")
    typer.echo(f"Expected clauses      : {stats.expected_clauses}")
    typer.echo(f"Exact matches         : {stats.exact_matches}")
    typer.echo(f"Normalized matches    : {stats.normalized_matches}")
    typer.echo(f"Annex matches         : {stats.annex_matches}")
    typer.echo(f"Low-confidence       : {stats.low_confidence_matches}")
    typer.echo(f"Inferred matches      : {stats.inferred_matches}")
    typer.echo(f"Missing               : {stats.missing}")
    typer.echo(f"Conflicting           : {stats.conflicting}")
    typer.echo(f"Unassigned ranges     : {stats.unassigned_ranges}")
    typer.echo(f"Alignment document    : {target}")


@align_app.command("inspect")
def inspect_alignment(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of a persisted alignment result."),
    ],
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            "-w",
            help="Standards Atlas workspace directory.",
        ),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    show_missing: Annotated[
        bool,
        typer.Option("--show-missing", help="Print missing and inferred clauses."),
    ] = cli_defaults.DEFAULT_FALSE,
    reviewed: Annotated[
        bool,
        typer.Option("--reviewed", help="Inspect reviewed.json instead of alignment.json."),
    ] = cli_defaults.DEFAULT_FALSE,
    show_conflicts: Annotated[
        bool,
        typer.Option("--show-conflicts", help="Print alignment issues."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Inspect a persisted alignment result."""
    try:
        result = (
            AlignmentReviewService(workspace).load_reviewed(document_key)
            if reviewed
            else AlignmentService(workspace).load(document_key)
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source       : {result.source_id}")
    typer.echo(f"Expected clauses      : {stats.expected_clauses}")
    typer.echo(f"Exact matches         : {stats.exact_matches}")
    typer.echo(f"Normalized matches    : {stats.normalized_matches}")
    typer.echo(f"Annex matches         : {stats.annex_matches}")
    typer.echo(f"Low-confidence       : {stats.low_confidence_matches}")
    typer.echo(f"Inferred matches      : {stats.inferred_matches}")
    typer.echo(f"Missing               : {stats.missing}")
    typer.echo(f"Unassigned ranges     : {stats.unassigned_ranges}")
    typer.echo(f"Issues                : {len(result.issues)}")
    if show_missing:
        for clause in result.clauses:
            if clause.status.value in {"missing", "low_confidence", "sequence_inferred"}:
                typer.echo(
                    f"{clause.status.value:18} {clause.expected_reference:12} {clause.clause_id}"
                )
    if show_conflicts:
        for issue in result.issues:
            if issue.severity in {"warning", "error"}:
                typer.echo(f"{issue.severity:7} {issue.code:28} {issue.message}")


@align_app.command("review")
def generate_alignment_review(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the automatic alignment to review."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    context_before: Annotated[
        int,
        typer.Option("--context-before", min=0, help="Items shown before a problem."),
    ] = cli_defaults.DEFAULT_ALIGNMENT_CONTEXT_BEFORE,
    context_after: Annotated[
        int,
        typer.Option("--context-after", min=0, help="Items shown after a problem."),
    ] = cli_defaults.DEFAULT_ALIGNMENT_CONTEXT_AFTER,
) -> None:
    """Generate Markdown review context and an override YAML template."""
    try:
        review_path, overrides_path = AlignmentReviewService(workspace).generate_review(
            document_key,
            context_before=context_before,
            context_after=context_after,
        )
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Review document       : {review_path}")
    typer.echo(f"Override document     : {overrides_path}")


@align_app.command("review-export")
def export_full_alignment_review(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the automatic alignment to export for review."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    reset_edited: Annotated[
        bool,
        typer.Option(
            "--reset-edited",
            help="Replace the editable review with the newly generated version.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Export the complete normalized document as editable review Markdown."""
    try:
        generated, edited = AlignmentReviewService(workspace).export_full_document_review(
            document_key,
            reset_edited=reset_edited,
        )
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Generated review      : {generated}")
    typer.echo(f"Editable review       : {edited}")


@align_app.command("review-validate")
def validate_full_alignment_review(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the edited full-document review."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Validate that the edited review changes alignment markers only."""
    try:
        diff = AlignmentReviewService(workspace).validate_full_document_review(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Alignment changes     : {len(diff.changes)}")
    typer.echo("Reviewed Markdown is valid.")


@align_app.command("review-diff")
def diff_full_alignment_review(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the edited full-document review."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Show structural changes made in the editable review Markdown."""
    try:
        diff = AlignmentReviewService(workspace).diff_full_document_review(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    counts: dict[str, int] = {}
    for change in diff.changes:
        counts[change.kind.value] = counts.get(change.kind.value, 0) + 1
    for kind, count in sorted(counts.items()):
        typer.echo(f"{kind:22}: {count}")
    if not counts:
        typer.echo("No review changes detected.")


@align_app.command("review-import")
def import_full_alignment_review(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the edited full-document review."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Translate edited Markdown alignment markers into overrides.yaml."""
    try:
        path = AlignmentReviewService(workspace).import_full_document_review(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Override document     : {path}")


@align_app.command("validate-overrides")
def validate_alignment_overrides(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the alignment override document."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Validate manual alignment decisions without applying them."""
    try:
        result = AlignmentReviewService(workspace).validate_overrides(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    if result.valid:
        typer.echo("Alignment overrides are valid.")
        return
    for issue in result.issues:
        typer.echo(f"{issue.severity:7} {issue.code:30} {issue.message}")
    raise typer.Exit(code=2)


@align_app.command("review-apply")
def apply_alignment_overrides(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the alignment override document."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Apply validated overrides and persist reviewed.json."""
    service = AlignmentReviewService(workspace)
    try:
        result = service.apply_overrides(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source       : {result.source_id}")
    typer.echo(f"Missing               : {stats.missing}")
    typer.echo(f"Low-confidence       : {stats.low_confidence_matches}")
    typer.echo(f"Inferred matches      : {stats.inferred_matches}")
    typer.echo(f"Reviewed alignment    : {service.reviewed_path(document_key)}")


@app.command()
def validate() -> None:
    """Validate the current Standards Atlas workspace."""
    typer.echo("Validation is not implemented yet.")
    raise typer.Exit(code=0)


@app.command()
def trace() -> None:
    """Inspect traceability information."""
    typer.echo("Traceability inspection is not implemented yet.")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
