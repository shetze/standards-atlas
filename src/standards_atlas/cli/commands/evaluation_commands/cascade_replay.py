"""Read-only offline diagnostics for qualification cascades."""

from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import typer
import yaml

from standards_atlas.application.semantic_qualification.cascade_replay import (
    CascadeReplayMode,
    replay_cascade,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("cascade-replay")
def replay_cascade_command(
    run: Annotated[Path, typer.Option("--run", exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output", help="New, separate report directory.")],
    mode: Annotated[
        CascadeReplayMode,
        typer.Option(
            "--mode", help="Historical inspection, corrected routing, or local proposals."
        ),
    ] = CascadeReplayMode.ROUTING,
    manifest: Annotated[
        Path | None,
        typer.Option("--manifest", exists=True, readable=True),
    ] = None,
    runs_output: Annotated[
        Path | None,
        typer.Option(
            "--runs-output",
            exists=True,
            file_okay=False,
            help="Original qualification proposal root; required for proposals mode.",
        ),
    ] = None,
    resources: Annotated[
        Path,
        typer.Option("--resources", exists=True, file_okay=False),
    ] = cli_defaults.DEFAULT_EVALUATION_RESOURCES,
) -> None:
    """Replay immutable qualification evidence without starting a model server.

    This is not a fresh qualification run. Missing observations are explicitly
    reported as requires_inference; source artifacts and public enrichments
    are never modified. An existing output directory is not overwritten.
    """
    try:
        json_path, markdown_path = replay_cascade(
            run=run,
            output_directory=output,
            mode=mode,
            manifest_path=manifest,
            runs_output=runs_output,
            resources=resources,
        )
    except (OSError, ValueError, KeyError, BadZipFile, yaml.YAMLError) as exc:
        typer.echo(f"Cascade replay failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Cascade replay JSON     : {json_path}")
    typer.echo(f"Cascade replay report   : {markdown_path}")
    typer.echo("Model inference         : none (offline replay)")
