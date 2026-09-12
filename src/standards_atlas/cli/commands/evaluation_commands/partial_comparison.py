"""Controlled comparisons for experimental Slice-6 policies and model inputs."""

from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import typer
import yaml

from standards_atlas.application.semantic_qualification.acceptance_profiles import (
    PartialAcceptanceProfile,
)
from standards_atlas.application.semantic_qualification.partial_comparison import (
    compare_efficient_prompts,
    compare_partial_profiles,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.cli import defaults
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.cli.commands.evaluation_commands.partial_cascade import partial_gateway_context


@evaluation_app.command("partial-profile-compare")
def compare_partial_profiles_command(
    experiment: Annotated[Path, typer.Option("--experiment", exists=True)],
    profiles: Annotated[
        str, typer.Option("--profiles", help="Comma-separated profile YAML paths.")
    ],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    resources: Annotated[Path, typer.Option("--resources", file_okay=False)] = (
        defaults.DEFAULT_EVALUATION_RESOURCES
    ),
) -> None:
    """Replay original Efficient observations only; no model calls or automatic adoption."""
    try:
        paths = [Path(p.strip()) for p in profiles.split(",") if p.strip()]
        result = compare_partial_profiles(
            experiment=experiment,
            profiles=tuple(PartialAcceptanceProfile.load(p) for p in paths),
            output_directory=output,
            resources=resources,
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
        typer.echo(f"Partial profile comparison failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    for variant in result["variants"]:
        typer.echo(f"{variant['id']}: {variant['diagnostics']['completed_clause_count']} completed")
    typer.echo(f"Report: {output / 'partial-profile-comparison.json'}")
    typer.echo("No new inference; candidate acceptance is not semantic qualification.")


@evaluation_app.command("partial-efficient-compare")
def compare_efficient_prompts_command(
    manifest: Annotated[Path, typer.Option("--manifest", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    run: Annotated[Path | None, typer.Option("--run", exists=True)] = None,
    dataset: Annotated[Path | None, typer.Option("--dataset", exists=True, dir_okay=False)] = None,
    prompts: Annotated[str, typer.Option("--prompts")] = (
        "taxonomy-partial-v2,taxonomy-partial-v3-no-process-null,taxonomy-partial-v4"
    ),
    acceptance_profile: Annotated[
        Path | None, typer.Option("--acceptance-profile", exists=True, dir_okay=False)
    ] = None,
    checks: Annotated[Path | None, typer.Option("--checks", exists=True, dir_okay=False)] = None,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 50,
    execute: Annotated[bool, typer.Option("--execute")] = False,
    require_taxonomy_decisions: Annotated[
        bool, typer.Option("--require-taxonomy-decisions")
    ] = False,
    resources: Annotated[Path, typer.Option("--resources", file_okay=False)] = (
        defaults.DEFAULT_EVALUATION_RESOURCES
    ),
    config: Annotated[Path, typer.Option("--config")] = defaults.DEFAULT_LLM_CONFIG,
    mcp_config: Annotated[Path, typer.Option("--mcp-config")] = defaults.DEFAULT_MCP_CONFIG,
) -> None:
    """Compare all configured Efficient models; no intermediate/final or detail-policy calls."""
    try:
        result = compare_efficient_prompts(
            manifest=QualificationMatrixManifest.load(manifest),
            run=run,
            dataset=dataset,
            prompts=tuple(p.strip() for p in prompts.split(",") if p.strip()),
            output_directory=output,
            resources=resources,
            limit=limit,
            execute=execute,
            gateway_context=lambda model: partial_gateway_context(
                model, config=config, mcp_config=mcp_config
            ),
            acceptance_profile=(
                PartialAcceptanceProfile.load(acceptance_profile) if acceptance_profile else None
            ),
            checks=checks,
            require_taxonomy_decisions=require_taxonomy_decisions,
            progress=typer.echo,
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
        typer.echo(f"Efficient comparison failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    for variant in result["variants"]:
        typer.echo(f"{variant['prompt']}: {variant['metrics']}")
    typer.echo(f"Report: {output / 'efficient-comparison.json'}")
    typer.echo("First-N experimental comparison; no semantic release or final applicability claim.")
