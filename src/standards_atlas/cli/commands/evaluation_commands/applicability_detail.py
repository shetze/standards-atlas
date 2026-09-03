"""CLI for sparse applicability-detail enrichment after final Presence consensus."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Protocol

import typer

from standards_atlas.adapters.llm import (
    LlmConfig,
    OpenAICompatibleLlmGateway,
    RamaLamaServerManager,
)
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    APPLICABILITY_DETAIL_ARTIFACT_DIRECTORY,
    APPLICABILITY_DETAIL_FAILURES_FILENAME,
    APPLICABILITY_DETAIL_REPORT_FILENAME,
    APPLICABILITY_DETAIL_SELECTION_FILENAME,
    ApplicabilityDetailEnrichmentReport,
    ApplicabilityDetailEnrichmentService,
    build_applicability_detail_selection,
    load_applicability_detail_report,
    persist_applicability_detail_report,
    persist_applicability_detail_selection,
)
from standards_atlas.application.semantic_qualification.consensus import ConsensusReport
from standards_atlas.application.semantic_qualification.proposals import SemanticTaskRepository
from standards_atlas.application.semantic_qualification.qualification_coverage import (
    QUALIFICATION_COVERAGE_FILENAME,
    load_qualification_coverage,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QUALIFICATION_SELECTION_FILENAME,
    ensure_qualification_run_snapshots,
    examples_for_persisted_selection,
    load_qualification_run_selection,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.domain.model import ApplicabilityFunction


class _RunningStatus(Protocol):
    running: bool


class _DetailServer(Protocol):
    def status(self) -> _RunningStatus: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


@contextmanager
def _managed_detail_server(
    server: _DetailServer,
    *,
    inference_required: bool,
    enabled: bool,
) -> Iterator[None]:
    """Stop only a RamaLama runtime started for this detail invocation."""
    started_for_run = False
    try:
        if inference_required and enabled and not server.status().running:
            server.start()
            started_for_run = True
        yield
    finally:
        if started_for_run:
            server.stop()


@evaluation_app.command("applicability-detail-enrich")
def enrich_applicability_details(
    manifest_path: Annotated[Path, typer.Option("--manifest", exists=True, readable=True)],
    run_directory: Annotated[
        Path,
        typer.Option(
            "--run",
            file_okay=False,
            help="Qualification matrix run directory containing qualification-selection.json.",
        ),
    ],
    consensus_path: Annotated[
        Path | None,
        typer.Option(
            "--consensus",
            exists=True,
            readable=True,
            dir_okay=False,
            help="Override the final consensus-report.json selected by the manifest.",
        ),
    ] = None,
    resources: Annotated[Path, typer.Option("--resources", file_okay=False)] = (
        cli_defaults.DEFAULT_EVALUATION_RESOURCES
    ),
    config_path: Annotated[Path, typer.Option("--config", exists=True, readable=True)] = (
        cli_defaults.DEFAULT_LLM_CONFIG
    ),
    corpus_root: Annotated[Path, typer.Option("--corpus-root", file_okay=False)] = (
        cli_defaults.DEFAULT_EVALUATION_CORPUS_ROOT
    ),
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Regenerate every selected detail result with the LLM cache disabled.",
        ),
    ] = False,
) -> None:
    """Enrich only clauses selected by final applicability-presence consensus."""
    manifest = QualificationMatrixManifest.load(manifest_path)
    detail_config = manifest.applicability_detail_enrichment
    if not detail_config.enabled:
        raise typer.BadParameter("applicability detail enrichment is disabled in the manifest")
    if detail_config.model is None:
        raise typer.BadParameter("applicability detail enrichment has no configured model")

    model = next((item for item in manifest.models if item.id == detail_config.model), None)
    if model is None:
        raise typer.BadParameter(
            f"applicability detail model {detail_config.model!r} is absent from manifest.models"
        )
    if model.provider != "ramalama":
        raise typer.BadParameter(
            "applicability detail enrichment currently requires a ramalama model; "
            f"got {model.provider!r} for {model.id}"
        )
    if not model.model_ref:
        raise typer.BadParameter(f"applicability detail model {model.id!r} has no model_ref")

    selection_path = run_directory / QUALIFICATION_SELECTION_FILENAME
    if not selection_path.is_file():
        raise typer.BadParameter(
            "qualification clause selection not found; run qualification-matrix first: "
            f"{selection_path}"
        )
    run_selection = load_qualification_run_selection(selection_path)
    ensure_qualification_run_snapshots(
        selection_root=run_directory,
        selection=run_selection,
        corpus_root=corpus_root,
    )
    if (
        run_selection.task != manifest.task
        or run_selection.dataset_version != manifest.dataset_version
        or run_selection.corpus_id != manifest.corpus_id
    ):
        raise typer.BadParameter(
            "persisted qualification selection does not match the qualification manifest"
        )
    examples = examples_for_persisted_selection(
        selection_root=run_directory,
        selection=run_selection,
    )

    resolved_consensus_path = consensus_path or (
        manifest.consensus.output_directory / manifest.matrix_id / "consensus-report.json"
    )
    if not resolved_consensus_path.is_file():
        raise typer.BadParameter(
            f"final qualification consensus not found: {resolved_consensus_path}"
        )
    consensus = ConsensusReport.model_validate_json(
        resolved_consensus_path.read_text(encoding="utf-8")
    )
    expected_prompt_selection = manifest.consensus.prompt_selection.model_dump()
    if (
        consensus.matrix_id != manifest.matrix_id
        or consensus.corpus_id != manifest.corpus_id
        or consensus.prompt_id != manifest.consensus.prompt_id
        or consensus.reasoning_mode_id != manifest.consensus.reasoning_mode_id
        or consensus.prompt_selection != expected_prompt_selection
    ):
        raise typer.BadParameter(
            "final qualification consensus does not match the qualification manifest"
        )

    coverage_path = run_directory / QUALIFICATION_COVERAGE_FILENAME
    if not coverage_path.is_file():
        raise typer.BadParameter(f"qualification coverage not found: {coverage_path}")
    coverage = load_qualification_coverage(coverage_path)

    task, canonical_schema = SemanticTaskRepository(resources / "tasks").load(
        detail_config.task,
        detail_config.task_version,
    )
    prompt = PromptRepository(resources / "prompts").load(
        detail_config.task,
        detail_config.prompt_version,
    )
    expected_functions = tuple(item.value for item in ApplicabilityFunction)
    if task.applicability_taxonomy != expected_functions:
        raise typer.BadParameter(
            "applicability detail task ontology differs from the domain taxonomy: "
            f"{task.applicability_taxonomy!r} != {expected_functions!r}"
        )

    try:
        selection = build_applicability_detail_selection(
            run_selection=run_selection,
            examples=examples,
            consensus=consensus,
            coverage=coverage,
            task_version=detail_config.task_version,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    detail_selection_path = run_directory / APPLICABILITY_DETAIL_SELECTION_FILENAME
    report_path = run_directory / APPLICABILITY_DETAIL_REPORT_FILENAME
    failure_path = run_directory / APPLICABILITY_DETAIL_FAILURES_FILENAME
    artifact_root = run_directory / APPLICABILITY_DETAIL_ARTIFACT_DIRECTORY
    if fresh:
        shutil.rmtree(artifact_root, ignore_errors=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    persist_applicability_detail_selection(selection, detail_selection_path)

    existing = None
    if report_path.is_file() and not fresh:
        existing = load_applicability_detail_report(report_path)

    llm_config = LlmConfig.load(config_path)
    llm_config = replace(
        llm_config,
        model=model.model_ref,
        timeout_seconds=detail_config.timeout_seconds,
        cache_directory=None if fresh else llm_config.cache_directory,
        server=replace(llm_config.server, model=model.model_ref),
    )
    gateway = OpenAICompatibleLlmGateway(llm_config)
    service = ApplicabilityDetailEnrichmentService(
        gateway,
        config=detail_config,
        prompt=prompt,
        canonical_schema=canonical_schema,
        model_id=model.id,
        model_ref=model.model_ref,
        artifact_root=artifact_root,
    )

    last_processed = 0

    def checkpoint(report: ApplicabilityDetailEnrichmentReport) -> None:
        nonlocal last_processed
        persist_applicability_detail_report(report, report_path, failure_path)
        if report.processed_clause_count > last_processed:
            latest = report.clauses[-1]
            typer.echo(
                "Applicability detail    : "
                f"{report.processed_clause_count}/{report.selected_clause_count} "
                f"{latest.document_key}/{latest.clause_id} {latest.outcome.value}"
            )
            last_processed = report.processed_clause_count

    pending_clause_count = service.pending_clause_count(
        selection=selection,
        existing=existing,
        fresh=fresh,
    )
    server = RamaLamaServerManager(llm_config)
    with _managed_detail_server(
        server,
        inference_required=bool(pending_clause_count),
        enabled=llm_config.server.enabled,
    ):
        report = service.enrich(
            selection=selection,
            examples=examples,
            existing=existing,
            fresh=fresh,
            checkpoint=checkpoint,
        )
    persist_applicability_detail_report(report, report_path, failure_path)

    typer.echo(f"Final Presence consensus : {resolved_consensus_path}")
    typer.echo(f"Selected clauses         : {report.selected_clause_count}")
    typer.echo(f"Pending inference        : {pending_clause_count}")
    typer.echo(f"Qualified clauses        : {selection.source_qualified_clause_count}")
    typer.echo(f"Unqualified clauses      : {selection.source_unqualified_clause_count}")
    typer.echo(f"Enriched clauses         : {report.enriched_clause_count}")
    typer.echo(f"Unresolved details       : {report.unresolved_clause_count}")
    typer.echo(f"Presence not confirmed   : {report.not_confirmed_clause_count}")
    typer.echo(f"Failed clauses           : {report.failed_clause_count}")
    typer.echo(f"Reused clauses           : {report.run_statistics.reused_clause_count}")
    typer.echo(f"Fresh predictions        : {report.run_statistics.fresh_prediction_count}")
    typer.echo(f"Cached predictions       : {report.run_statistics.cached_prediction_count}")
    typer.echo(f"Detail selection         : {detail_selection_path}")
    typer.echo(f"Detail report            : {report_path}")
    typer.echo(f"Failure report           : {failure_path}")
