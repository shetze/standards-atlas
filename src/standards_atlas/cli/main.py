"""Command-line interface for Standards Atlas."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas import __version__
from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.adapters.docling import (
    DoclingArtifactRepository,
    DoclingJsonReader,
    DoclingNotInstalledError,
    DoclingPdfConverter,
    DocumentConversionError,
    ExtractionState,
)
from standards_atlas.adapters.doorstop import (
    DoorstopExportConfig,
    DoorstopExporter,
)
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
from standards_atlas.application.services import (
    DocumentExportService,
    DocumentExtractionService,
    DocumentImportService,
    DocumentNormalizationService,
    ExtractionInspectionService,
    ReferenceCandidateService,
)
from standards_atlas.application.services.atlasdata_toc_service import AtlasDataTocService
from standards_atlas.cli.printers import print_document_summary
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

docling_app = typer.Typer(
    help="Convert and inspect private PDF extraction artefacts with Docling.",
    no_args_is_help=True,
)

app.add_typer(docling_app, name="docling")

normalize_app = typer.Typer(
    help="Normalize extracted documents before semantic alignment.",
    no_args_is_help=True,
)
app.add_typer(normalize_app, name="normalize")

reference_app = typer.Typer(
    help="Detect and inspect clause-reference candidates.",
    no_args_is_help=True,
)
app.add_typer(reference_app, name="references")

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


@docling_app.command("convert")
def convert_pdf_with_docling(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            resolve_path=True,
            help="PDF file to convert.",
        ),
    ],
    document_key: Annotated[
        str,
        typer.Option("--document", "-d", help="Key used below .atlas/docling/."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = Path(".atlas"),
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace an existing native Docling document."),
    ] = False,
) -> None:
    """Convert a PDF and persist native Docling JSON below the private workspace."""
    repository = DoclingArtifactRepository(workspace)
    converter = DoclingPdfConverter()
    service = DocumentExtractionService(converter, DoclingJsonReader())

    try:
        state = repository.extraction_state(document_key, file)
        if state is ExtractionState.CURRENT and not overwrite:
            typer.echo("Existing extraction matches the source PDF.")
            typer.echo(f"Docling document      : {repository.document_path(document_key)}")
            return
        if state is ExtractionState.STALE and not overwrite:
            typer.echo(
                "The source PDF has changed since the last conversion. "
                "Use --overwrite to update the extraction.",
                err=True,
            )
            raise typer.Exit(code=3)
        if state is ExtractionState.INCOMPLETE and not overwrite:
            typer.echo(
                "The persisted extraction is incomplete. Use --overwrite to repair it.",
                err=True,
            )
            raise typer.Exit(code=3)

        target = repository.document_path(document_key)
        generated = service.convert(file, target, overwrite=overwrite)
        repository.save_metadata(document_key, converter.conversion_metadata(file))
    except (DoclingNotInstalledError, DocumentConversionError, FileExistsError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Converted PDF         : {file}")
    typer.echo(f"Document key          : {document_key}")
    typer.echo(f"Docling document      : {generated}")
    typer.echo(f"Conversion metadata   : {repository.metadata_path(document_key)}")


@docling_app.command("inspect")
def inspect_docling_document(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of a persisted Docling document."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = Path(".atlas"),
) -> None:
    """Inspect extraction coverage without loading the Docling runtime."""
    repository = DoclingArtifactRepository(workspace)
    try:
        source = repository.document_path(document_key)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    if not source.exists():
        typer.echo(f"No Docling document found for key: {document_key}", err=True)
        raise typer.Exit(code=1)

    extracted = DoclingJsonReader().read(source)
    statistics = ExtractionInspectionService().inspect(extracted)
    typer.echo(f"Document source       : {extracted.source_id}")
    typer.echo(f"Pages                 : {statistics.page_count}")
    typer.echo(f"Extracted items       : {statistics.item_count}")
    typer.echo(f"Items with page data  : {statistics.items_with_page_evidence}")
    typer.echo(f"Items without page data: {statistics.items_without_page_evidence}")
    typer.echo(f"Unknown items         : {statistics.unknown_item_count}")
    for item_type, count in statistics.counts_by_type.items():
        typer.echo(f"{item_type.capitalize():22}: {count}")
    if statistics.unknown_labels:
        typer.echo(f"Unknown labels        : {', '.join(statistics.unknown_labels)}")


@normalize_app.command("run")
def normalize_extracted_document(
    document_key: Annotated[str, typer.Argument(help="Key of a persisted Docling document.")],
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
    ] = Path(".atlas"),
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing normalized document.")
    ] = False,
) -> None:
    """Normalize an extracted document and persist the result below .atlas."""
    repository = NormalizationArtifactRepository(workspace)
    target = repository.document_path(document_key)
    if target.exists() and not overwrite:
        typer.echo("A normalized document already exists. Use --overwrite to replace it.", err=True)
        raise typer.Exit(code=3)
    try:
        result = DocumentNormalizationService(workspace=workspace).normalize(document_key)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source             : {result.source_id}")
    typer.echo(f"Input items                 : {stats.input_items}")
    typer.echo(f"Output items                : {stats.output_items}")
    typer.echo(f"Headers suppressed          : {stats.headers_suppressed}")
    typer.echo(f"Footers suppressed          : {stats.footers_suppressed}")
    typer.echo(f"Page numbers suppressed     : {stats.page_numbers_suppressed}")
    typer.echo(f"Hyphenations repaired       : {stats.hyphenations_repaired}")
    typer.echo(f"Text fragments merged       : {stats.text_fragments_merged}")
    typer.echo(f"Lists normalized            : {stats.lists_normalized}")
    typer.echo(f"Code blocks                 : {stats.code_blocks}")
    typer.echo(f"Normalized document         : {target}")


@normalize_app.command("inspect")
def inspect_normalized_document(
    document_key: Annotated[str, typer.Argument(help="Key of a normalized document.")],
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
    ] = Path(".atlas"),
) -> None:
    """Inspect normalization statistics and diagnostics."""
    try:
        result = NormalizationArtifactRepository(workspace).load(document_key)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source             : {result.source_id}")
    typer.echo(f"Input items                 : {stats.input_items}")
    typer.echo(f"Output items                : {stats.output_items}")
    typer.echo(f"Suppressed items            : {len(result.suppressed_items)}")
    typer.echo(f"Normalization issues        : {len(result.issues)}")
    typer.echo(f"Code blocks                 : {stats.code_blocks}")


@reference_app.command("detect")
def detect_reference_candidates(
    document_key: Annotated[
        str,
        typer.Argument(
            help="Key of the normalized and engineering document.",
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
    """Detect clause-reference candidates and validate them against AtlasData structure."""
    try:
        result = ReferenceCandidateService(workspace).detect(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source       : {result.source_id}")
    typer.echo(f"Input items           : {stats.input_items}")
    typer.echo(f"Candidates            : {stats.candidates}")
    typer.echo(f"Expected              : {stats.expected_candidates}")
    typer.echo(f"Unexpected            : {stats.unexpected_candidates}")
    typer.echo(f"Ambiguous             : {stats.ambiguous_candidates}")
    typer.echo(f"Exact matches         : {stats.exact_matches}")
    typer.echo(f"Normalized matches    : {stats.normalized_matches}")
    typer.echo(f"Annex matches         : {stats.annex_matches}")

    repository = ReferenceCandidateRepository(workspace)
    document_path = repository.document_path(document_key)
    typer.echo(f"Candidate document    : {document_path}")


@reference_app.command("inspect")
def inspect_reference_candidates(
    document_key: Annotated[str, typer.Argument(help="Key of a persisted candidate document.")],
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
    ] = Path(".atlas"),
    show_unexpected: Annotated[
        bool, typer.Option("--show-unexpected", help="Print unexpected and ambiguous candidates.")
    ] = False,
) -> None:
    """Inspect persisted clause-reference candidates."""
    try:
        result = ReferenceCandidateService(workspace).load(document_key)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source       : {result.source_id}")
    typer.echo(f"Candidates            : {stats.candidates}")
    typer.echo(f"Expected              : {stats.expected_candidates}")
    typer.echo(f"Unexpected            : {stats.unexpected_candidates}")
    typer.echo(f"Ambiguous             : {stats.ambiguous_candidates}")
    typer.echo(f"Issues                : {len(result.issues)}")
    if show_unexpected:
        for candidate in result.candidates:
            if candidate.status.value != "expected":
                typer.echo(
                    f"{candidate.sequence_number:5} {candidate.status.value:10} "
                    f"{candidate.normalized_reference:12} {candidate.title_remainder or ''}"
                )


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
