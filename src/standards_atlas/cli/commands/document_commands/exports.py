"""CLI command group extracted without behavioral changes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.doorstop import DoorstopExportConfig, DoorstopExporter
from standards_atlas.adapters.filesystem import (
    FileSystemEngineeringDocumentRepository,
    FileSystemPublicationDocumentProvider,
)
from standards_atlas.application.services import DocumentExportService
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import document_export_app
from standards_atlas.cli.composition import build_markdown_export_service


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
    part: Annotated[
        list[str] | None,
        typer.Option("--part", help="Physical part key; repeat for a family publication."),
    ] = cli_defaults.DEFAULT_NONE,
    family_title: Annotated[
        str | None,
        typer.Option("--title", help="Logical family title used for runtime composition."),
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
            part_keys=tuple(part or ()),
            family_title=family_title,
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
                "Defaults to .atlas/work/doorstop/<document-key>."
            ),
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = cli_defaults.DEFAULT_NONE,
    part: Annotated[
        list[str] | None,
        typer.Option("--part", help="Physical part key; repeat for a family publication."),
    ] = cli_defaults.DEFAULT_NONE,
    family_title: Annotated[
        str | None,
        typer.Option("--title", help="Logical family title used for runtime composition."),
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
    repository = FileSystemEngineeringDocumentRepository(workspace=workspace)
    publications = FileSystemPublicationDocumentProvider(repository)

    try:
        document = publications.load(
            document_key,
            part_keys=tuple(part or ()),
            family_title=family_title,
        )
    except FileNotFoundError:
        typer.echo(f"No persisted document found for key: {document_key}", err=True)
        raise typer.Exit(code=1) from None

    export_target = (
        target
        if target is not None
        else cli_defaults.DEFAULT_WORK_ROOT / "doorstop" / document.key.value
    )
    doorstop_workspace = export_target.parent

    config = DoorstopExportConfig(
        workspace=doorstop_workspace,
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


@document_export_app.command("gemara")
def export_document_to_gemara(
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
            help="Target YAML file. Defaults to local/exports/gemara/<document-key>.yaml.",
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ] = cli_defaults.DEFAULT_NONE,
    part: Annotated[
        list[str] | None,
        typer.Option("--part", help="Physical part key; repeat for a family publication."),
    ] = cli_defaults.DEFAULT_NONE,
    family_title: Annotated[
        str | None,
        typer.Option("--title", help="Logical family title used for runtime composition."),
    ] = cli_defaults.DEFAULT_NONE,
    gemara_version: Annotated[
        str,
        typer.Option("--gemara-version", help="Gemara specification version declared in metadata."),
    ] = "v0.17.0-dev",
    replace_existing: Annotated[
        bool,
        typer.Option("--replace/--no-replace", help="Replace an existing Gemara YAML export."),
    ] = cli_defaults.DEFAULT_TRUE,
) -> None:
    """Export a persisted document or family as a Gemara GuidanceCatalog."""
    from standards_atlas.adapters.gemara import GemaraGuidanceExporter, GemaraGuidanceMapper

    repository = FileSystemEngineeringDocumentRepository(workspace=workspace)
    publications = FileSystemPublicationDocumentProvider(repository)
    try:
        document = publications.load(
            document_key,
            part_keys=tuple(part or ()),
            family_title=family_title,
        )
    except FileNotFoundError:
        typer.echo(f"No persisted document found for key: {document_key}", err=True)
        raise typer.Exit(code=1) from None

    export_target = target or Path("local/exports/gemara") / f"{document.key.value}.yaml"
    if export_target.exists() and not replace_existing:
        typer.echo(f"Gemara target already exists: {export_target}", err=True)
        raise typer.Exit(code=2)

    exporter = GemaraGuidanceExporter(mapper=GemaraGuidanceMapper(gemara_version=gemara_version))
    try:
        generated_path = DocumentExportService(exporter=exporter).export_document(
            document=document,
            target=export_target,
        )
    except ValueError as exc:
        typer.echo(f"Gemara export failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    typer.echo(f"Exported document     : {document.title}")
    typer.echo(f"Document key          : {document.key.value}")
    typer.echo(f"Clauses considered    : {len(document.clauses)}")
    typer.echo(f"Gemara target         : {generated_path}")
    typer.echo(f"Gemara version        : {gemara_version}")


@document_export_app.command("gemara-controls")
def export_document_to_gemara_controls(
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
            help=(
                "Target YAML file. Defaults to local/exports/gemara/<document-key>-controls.yaml."
            ),
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ] = cli_defaults.DEFAULT_NONE,
    part: Annotated[
        list[str] | None,
        typer.Option("--part", help="Physical part key; repeat for a family publication."),
    ] = cli_defaults.DEFAULT_NONE,
    family_title: Annotated[
        str | None,
        typer.Option("--title", help="Logical family title used for runtime composition."),
    ] = cli_defaults.DEFAULT_NONE,
    gemara_version: Annotated[
        str,
        typer.Option("--gemara-version", help="Gemara specification version declared in metadata."),
    ] = "v0.17.0-dev",
    replace_existing: Annotated[
        bool,
        typer.Option(
            "--replace/--no-replace",
            help="Replace an existing Gemara ControlCatalog export.",
        ),
    ] = cli_defaults.DEFAULT_TRUE,
) -> None:
    """Export qualified normative clauses as a Gemara ControlCatalog."""
    from standards_atlas.adapters.gemara import GemaraControlExporter, GemaraControlMapper

    repository = FileSystemEngineeringDocumentRepository(workspace=workspace)
    publications = FileSystemPublicationDocumentProvider(repository)
    try:
        document = publications.load(
            document_key,
            part_keys=tuple(part or ()),
            family_title=family_title,
        )
    except FileNotFoundError:
        typer.echo(f"No persisted document found for key: {document_key}", err=True)
        raise typer.Exit(code=1) from None

    export_target = target or Path("local/exports/gemara") / f"{document.key.value}-controls.yaml"
    if export_target.exists() and not replace_existing:
        typer.echo(f"Gemara target already exists: {export_target}", err=True)
        raise typer.Exit(code=2)

    exporter = GemaraControlExporter(mapper=GemaraControlMapper(gemara_version=gemara_version))
    try:
        generated_path = DocumentExportService(exporter=exporter).export_document(
            document=document,
            target=export_target,
        )
    except ValueError as exc:
        typer.echo(f"Gemara control export failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    typer.echo(f"Exported document     : {document.title}")
    typer.echo(f"Document key          : {document.key.value}")
    typer.echo(f"Clauses considered    : {len(document.clauses)}")
    typer.echo(f"Gemara control target : {generated_path}")
    typer.echo(f"Gemara version        : {gemara_version}")
