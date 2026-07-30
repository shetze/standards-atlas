"""Command-line interface for Standards Atlas."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.application.workflow import (
    EndToEndWorkflowService,
    WorkflowRunReporter,
    WorkflowStage,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import (
    catalog_app,
    workflow_app,
)


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
