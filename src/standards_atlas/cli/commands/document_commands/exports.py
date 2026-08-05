"""CLI command group extracted without behavioral changes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.doorstop import DoorstopExportConfig, DoorstopExporter
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.services import DocumentExportService
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import document_export_app
from standards_atlas.cli.composition import build_markdown_export_service
from standards_atlas.domain.model import DocumentKey


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
    service = build_markdown_export_service(workspace)
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
