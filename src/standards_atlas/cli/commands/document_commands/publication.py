"""CLI command group extracted without behavioral changes."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.doorstop import (
    AVAILABLE_DOORSTOP_TEMPLATES,
    DoorstopTemplateInstaller,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import doorstop_app


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
