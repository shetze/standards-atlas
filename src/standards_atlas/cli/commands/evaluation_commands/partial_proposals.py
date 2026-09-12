"""Explicit opt-in partial inference experiments, separate from qualification."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import typer
import yaml

from standards_atlas.adapters.llm import (
    CodexCliConfig,
    CodexCliLlmGateway,
    LlmConfig,
    OpenAICompatibleLlmGateway,
    RamaLamaServerManager,
)
from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_ATTRIBUTES,
    ordered_attributes,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    load_partial_inputs,
    run_partial_proposals,
)
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialProposalConfig,
)
from standards_atlas.cli import defaults
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.cli.runtime_managers import managed_mcp_server


@evaluation_app.command("partial-proposals")
def propose_partial_semantics(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            file_okay=False,
            help="Separate experiment directory; identical runs can resume.",
        ),
    ],
    model: Annotated[str, typer.Option("--model", help="Model identity, including for planning.")],
    run: Annotated[
        Path | None,
        typer.Option(
            "--run",
            exists=True,
            readable=True,
            help="Qualification ZIP/directory; mutually exclusive with --dataset.",
        ),
    ] = None,
    dataset: Annotated[
        Path | None,
        typer.Option(
            "--dataset",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Source corpus dataset.json.",
        ),
    ] = None,
    attributes: Annotated[
        str | None,
        typer.Option(
            "--attributes", help="Comma-separated current attributes; omitted means all nine."
        ),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option(
            "--execute", help="Actually infer pending questions; default is model-free planning."
        ),
    ] = False,
    revalidate_responses: Annotated[
        bool,
        typer.Option(
            "--revalidate-responses",
            help="Revalidate saved failed responses; no inference unless --execute is also set.",
        ),
    ] = False,
    provider: Annotated[str, typer.Option("--provider")] = "ramalama",
    config: Annotated[Path, typer.Option("--config")] = defaults.DEFAULT_LLM_CONFIG,
    mcp_config: Annotated[Path, typer.Option("--mcp-config")] = defaults.DEFAULT_MCP_CONFIG,
    resources: Annotated[Path, typer.Option("--resources", file_okay=False)] = (
        defaults.DEFAULT_EVALUATION_RESOURCES
    ),
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            min=1,
            help="Explicit first-N subset, preserved on resume; not a pending-work limit.",
        ),
    ] = None,
    max_tokens: Annotated[int, typer.Option("--max-tokens", min=1)] = 512,
    temperature: Annotated[float, typer.Option("--temperature", min=0.0, max=2.0)] = 0.0,
    seed: Annotated[int, typer.Option("--seed")] = defaults.DEFAULT_EVALUATION_SEED,
    retry_attempts: Annotated[int, typer.Option("--retry-attempts", min=1)] = 3,
    retry_timeouts: Annotated[bool, typer.Option("--retry-timeouts/--no-retry-timeouts")] = False,
    truncation_retry_max_tokens: Annotated[
        int | None, typer.Option("--truncation-retry-max-tokens", min=1)
    ] = 1024,
) -> None:
    """Plan or run experimental partial observations; never route or publish results."""
    try:
        if provider not in {"ramalama", "codex"}:
            raise ValueError("provider must be ramalama or codex")
        selected = PARTIAL_ATTRIBUTES
        if attributes is not None:
            selected = ordered_attributes(tuple(part.strip() for part in attributes.split(",")))
        source_selection = load_partial_inputs(run=run, dataset=dataset)
        source = (run or dataset).resolve()
        destination = output.resolve()
        if destination == source or (source.is_dir() and destination.is_relative_to(source)):
            raise ValueError("partial output must be separate from the source run")
        experiment = PartialProposalConfig(
            corpus_id=source_selection.corpus_id,
            dataset_version=source_selection.dataset_version,
            provider=provider,
            model=model,
            selected_attributes=selected,
            limit=limit,
            max_tokens=max_tokens,
            temperature=temperature,
            seed=seed,
            retry_attempts=retry_attempts,
            retry_timeouts=retry_timeouts,
            truncation_retry_max_tokens=truncation_retry_max_tokens,
        )
        with ExitStack() as stack:

            def gateway_factory():
                if provider == "codex":
                    manager = managed_mcp_server(mcp_config)
                    stack.enter_context(manager.ensure_running(autostart=True, autostop=True))
                    return CodexCliLlmGateway(CodexCliConfig())
                base = LlmConfig.load(config)
                model_config = replace(base, model=model, server=replace(base.server, model=model))
                manager = RamaLamaServerManager(model_config)
                if model_config.server.enabled and not manager.status().running:
                    manager.start()
                    stack.callback(manager.stop)
                return OpenAICompatibleLlmGateway(model_config)

            report = run_partial_proposals(
                experiment,
                resources=resources,
                output_directory=output,
                examples=source_selection.examples,
                source_fingerprints=source_selection.fingerprints,
                execute=execute,
                revalidate_responses=revalidate_responses,
                gateway_factory=gateway_factory,
                progress=lambda text: typer.echo(text),
            )
    except (
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
        BadZipFile,
        yaml.YAMLError,
    ) as exc:
        typer.echo(f"Partial experiment failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"Selected / accounted     : {report['selected_count']} / {report['accounted_count']}"
    )
    typer.echo(f"Grouped requests planned : {report['planned_request_count']}")
    typer.echo(f"Gateway calls this time  : {report['request_timing']['request_count']}")
    typer.echo(f"Revalidated responses    : {report['revalidated_observation_count']}")
    typer.echo(f"Status counts            : {report['status_counts']}")
    typer.echo(f"Report                   : {output / 'partial-run-report.json'}")
    typer.echo("Experimental only; no production consensus, early exits or publication.")
