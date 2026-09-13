"""Frozen qualification campaigns around the existing partial-cascade workflow."""

from contextlib import contextmanager
from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import typer
import yaml

from standards_atlas.application.semantic_qualification.campaign_activation import (
    activate_campaign,
    archive_campaign,
)
from standards_atlas.application.semantic_qualification.campaign_evaluation import evaluate_campaign
from standards_atlas.application.semantic_qualification.campaign_execution import run_campaign
from standards_atlas.application.semantic_qualification.campaign_selection import (
    prepare_campaign,
    verify_prepared_campaign,
)
from standards_atlas.cli import defaults
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.cli.commands.evaluation_commands.partial_cascade import partial_gateway_context


@contextmanager
def _errors():
    try:
        yield
    except (
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
        BadZipFile,
        yaml.YAMLError,
    ) as exc:
        typer.echo(f"Partial qualification failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@evaluation_app.command("partial-qualification-prepare")
def prepare_qualification_command(
    manifest: Annotated[Path, typer.Option("--manifest", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    resources: Annotated[
        Path, typer.Option("--resources", file_okay=False)
    ] = defaults.DEFAULT_EVALUATION_RESOURCES,
    reuse_frozen: Annotated[bool, typer.Option("--reuse-frozen")] = False,
) -> None:
    """Freeze a proportional source sample, all published Golden cases and supplied reviews."""
    with _errors():
        if reuse_frozen and output.exists():
            result = verify_prepared_campaign(
                manifest=manifest, campaign=output, resources=resources
            )
        else:
            result = prepare_campaign(manifest=manifest, output=output, resources=resources)
    typer.echo(f"Frozen campaign: {result['campaign_sha256']}")
    typer.echo(f"Plan: {output / 'campaign-plan.json'}; no models started")


@evaluation_app.command("partial-qualification-run")
def run_qualification_command(
    campaign: Annotated[Path, typer.Option("--campaign", exists=True, file_okay=False)],
    phase: Annotated[
        str, typer.Option("--phase", help="all, end-to-end, fixed-detail, full")
    ] = "all",
    variant: Annotated[str | None, typer.Option("--variant")] = None,
    execute: Annotated[bool, typer.Option("--execute")] = False,
    resources: Annotated[
        Path, typer.Option("--resources", file_okay=False)
    ] = defaults.DEFAULT_EVALUATION_RESOURCES,
    config: Annotated[Path, typer.Option("--config")] = defaults.DEFAULT_LLM_CONFIG,
    mcp_config: Annotated[Path, typer.Option("--mcp-config")] = defaults.DEFAULT_MCP_CONFIG,
) -> None:
    """Run independent cache-disabled repetitions; full baseline is an explicit gated phase."""
    with _errors():
        result = run_campaign(
            campaign=campaign,
            resources=resources,
            phase=phase,
            variant_id=variant,
            execute=execute,
            progress=typer.echo,
            gateway_context=lambda model: partial_gateway_context(
                model, config=config, mcp_config=mcp_config, disable_cache=True
            ),
        )
    typer.echo(f"Mode: {result['run_mode']}; jobs: {len(result['jobs'])}")
    for job in result["jobs"]:
        typer.echo(f"{job['job']}: {job['status']}")
    typer.echo("Execution does not promote profiles. Evaluate the stored qualification evidence.")


@evaluation_app.command("partial-qualification-evaluate")
def evaluate_qualification_command(
    campaign: Annotated[Path, typer.Option("--campaign", exists=True, file_okay=False)],
    archive_output: Annotated[
        Path | None, typer.Option("--archive-output", file_okay=False)
    ] = None,
    fail_on_rejection: Annotated[bool, typer.Option("--fail-on-rejection")] = False,
    resources: Annotated[
        Path, typer.Option("--resources", file_okay=False)
    ] = defaults.DEFAULT_EVALUATION_RESOURCES,
) -> None:
    """Recheck raw evidence, final policy, semantic references, costs and independent repeats."""
    with _errors():
        result = evaluate_campaign(campaign=campaign, resources=resources)
        archive = (
            archive_campaign(campaign=campaign, output=archive_output, resources=resources)
            if archive_output is not None
            else None
        )
    typer.echo(f"Full baseline eligible: {result['pre_full_eligible']}")
    typer.echo(f"Activation eligible: {result['activation_eligible']}")
    typer.echo(f"80% observed on full population: {result['efficient_target_observed']}")
    report_path = (
        campaign / "evaluations" / result["evaluation_sha256"] / "qualification-evaluation.json"
    )
    typer.echo(f"Report: {report_path}")
    if archive:
        typer.echo(f"Evidence archive: {archive}")
    if fail_on_rejection and not result["activation_eligible"]:
        raise typer.Exit(code=1)


@evaluation_app.command("partial-qualification-activate")
def activate_qualification_command(
    campaign: Annotated[Path, typer.Option("--campaign", exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    reviewer: Annotated[str, typer.Option("--reviewer")],
    review_reference: Annotated[str, typer.Option("--review-reference")],
    allow_below_target: Annotated[bool, typer.Option("--allow-below-target")] = False,
    resources: Annotated[
        Path, typer.Option("--resources", file_okay=False)
    ] = defaults.DEFAULT_EVALUATION_RESOURCES,
) -> None:
    """Export an explicit reviewed run configuration only after rechecking all release gates."""
    with _errors():
        activate_campaign(
            campaign=campaign,
            output=output,
            resources=resources,
            reviewer=reviewer,
            review_reference=review_reference,
            allow_below_target=allow_below_target,
        )
    typer.echo(f"Explicit activation bundle: {output}")
    typer.echo("No project defaults, rules, Golden labels or public enrichments changed.")
