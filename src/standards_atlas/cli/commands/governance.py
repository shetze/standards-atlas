"""Governance selection profile commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.application.governance import (
    GovernanceSelectionProfileError,
    load_governance_selection_profile,
    render_governance_selection_profile,
)
from standards_atlas.cli.apps import governance_profile_app


@governance_profile_app.command("validate")
def validate_governance_profile(
    profile: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Selection profile YAML."),
    ],
) -> None:
    """Validate a governance selection profile."""
    try:
        loaded = load_governance_selection_profile(profile)
    except GovernanceSelectionProfileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Governance profile : {loaded.id}")
    typer.echo(f"Version            : {loaded.version}")
    typer.echo(f"Domain             : {loaded.context.domain}")
    typer.echo("Profile is valid")


@governance_profile_app.command("show")
def show_governance_profile(
    profile: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Selection profile YAML."),
    ],
) -> None:
    """Render the canonical normalized governance selection profile."""
    try:
        loaded = load_governance_selection_profile(profile)
    except GovernanceSelectionProfileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(render_governance_selection_profile(loaded), nl=False)
