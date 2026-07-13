"""Command-line interface for Standards Atlas."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas import __version__
from standards_atlas.cli.printers import print_document_summary
from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.services import DocumentImportService
from standards_atlas.application.services.atlasdata_toc_service import AtlasDataTocService
from standards_atlas.adapters.doorstop import (
    DoorstopExportConfig,
    DoorstopExporter,
)
from standards_atlas.adapters.filesystem import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.application.services import DocumentExportService
from standards_atlas.domain.model import DocumentKey

app = typer.Typer(
    name="standards-atlas",
    help="Semantic traceability platform for technical standards.",
    no_args_is_help=True,
)

inspect_app = typer.Typer(
    help="Inspect Standards Atlas artifacts for debugging and development.",
    no_args_is_help=True,
)

app.add_typer(inspect_app, name="inspect")

atlasdata_app = typer.Typer(
    help="Work with legacy AtlasData files.",
    no_args_is_help=True,
)

app.add_typer(atlasdata_app, name="atlasdata")

document_app = typer.Typer(
    help="Import, transform, and persist engineering documents.",
    no_args_is_help=True,
)

app.add_typer(document_app, name="document")

document_export_app = typer.Typer(
    help="Export persisted engineering documents.",
    no_args_is_help=True,
)

document_app.add_typer(
    document_export_app,
    name="export",
)

@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", "-v", help="Show the Standards Atlas version and exit."),
    ] = False,
) -> None:
    """Standards Atlas command-line entry point."""
    if version:
        typer.echo(f"standards-atlas {__version__}")
        raise typer.Exit()


@app.command()
def info() -> None:
    """Show basic project information."""
    typer.echo("Standards Atlas")
    typer.echo("Semantic traceability platform for technical standards.")


@inspect_app.command("data")
def inspect_data(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            resolve_path=True,
            help="Atlas data file to inspect.",
        ),
    ],
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-V", help="Show parsed clause details."),
    ] = False,
) -> None:
    """Inspect a legacy Atlas data file through the canonical domain model."""
    reader = AtlasDataImporter()
    service = DocumentImportService(reader)
    document = service.import_document(file)
    print_document_summary(document, source_file=file, verbose=verbose)


@atlasdata_app.command("generate-toc")
def generate_toc(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            resolve_path=True,
            help="AtlasData file to update.",
        ),
    ],
    write: Annotated[
        bool,
        typer.Option("--write", help="Write changes to the file."),
    ] = False,
) -> None:
    """Generate the TOC data section for an AtlasData file."""
    service = AtlasDataTocService()
    result = service.update_toc(file, write=write)

    typer.echo(f"File                  : {result.source.name}")
    typer.echo(f"Generated TOC records : {result.generated_toc_records}")
    typer.echo(f"Preserved headings    : {result.preserved_toc_headings}")
    typer.echo(f"Preserved TEXT records: {result.preserved_public_text_records}")
    typer.echo(f"Removed records       : {result.removed_records}")
    typer.echo(f"Changed               : {result.changed}")

    if write:
        if result.backup:
            typer.echo(f"Backup                : {result.backup.name}")
        else:
            typer.echo("Backup                : not created; file unchanged")
    else:
        typer.echo()
        typer.echo("Dry run only. Use --write to update the file.")


@document_app.command("import")
def import_document(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            resolve_path=True,
            help="Document source file to import.",
        ),
    ],
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            "-w",
            help="Standards Atlas workspace directory.",
        ),
    ] = Path(".atlas"),
) -> None:
    """Import an engineering document into the local Standards Atlas workspace."""
    importer = AtlasDataImporter()
    repository = FileSystemEngineeringDocumentRepository(workspace=workspace)

    service = DocumentImportService(
        importer=importer,
        repository=repository,
    )

    document = service.import_document(file)

    typer.echo(f"Imported document     : {document.title}")
    typer.echo(f"Key                   : {document.key.value}")
    typer.echo(f"Clauses               : {len(document.clauses)}")
    typer.echo(f"Workspace             : {workspace}")


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
    ] = Path(".atlas"),
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
    ] = None,
    prefix: Annotated[
        str | None,
        typer.Option(
            "--prefix",
            help="Doorstop document prefix.",
        ),
    ] = None,
    digits: Annotated[
        int,
        typer.Option(
            "--digits",
            min=1,
            help="Number of digits used for Doorstop item identifiers.",
        ),
    ] = 8,
    separator: Annotated[
        str,
        typer.Option(
            "--separator",
            help="Separator between Doorstop prefix and numeric identifier.",
        ),
    ] = "-",
    validate: Annotated[
        bool,
        typer.Option(
            "--validate/--no-validate",
            help="Validate the generated Doorstop document after export.",
        ),
    ] = True,
    replace_existing: Annotated[
        bool,
        typer.Option(
            "--replace/--no-replace",
            help="Replace an existing Doorstop export directory.",
        ),
    ] = True,
    initialize_git: Annotated[
        bool,
        typer.Option(
            "--init-git/--no-init-git",
            help="Initialize the Doorstop target as a Git repository.",
        ),
    ] = True,
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
            f"  standards-atlas document import <source> "
            f"--workspace {workspace}",
            err=True,
        )
        raise typer.Exit(code=1)

    document = repository.load(key)

    export_target = (
        target
        if target is not None
        else workspace / "doorstop" / document.key.value
    )

    config = DoorstopExportConfig(
        workspace=workspace / "doorstop",
        prefix=prefix,
        digits=digits,
        separator=separator,
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


@app.command()
def validate() -> None:
    """Validate the current Standards Atlas workspace."""
    typer.echo("Validation is not implemented yet.")
    raise typer.Exit(code=0)


@app.command()
def trace() -> None:
    """Inspect traceability information."""
    typer.echo("Traceability inspection is not implemented yet.")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
