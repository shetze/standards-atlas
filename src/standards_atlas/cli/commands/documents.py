"""Command-line interface for Standards Atlas."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.adapters.atlasdata.metadata import AtlasDataLifecycleStatus
from standards_atlas.adapters.doorstop import (
    AVAILABLE_DOORSTOP_TEMPLATES,
    DoorstopExportConfig,
    DoorstopExporter,
    DoorstopTemplateInstaller,
)
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.services import (
    AtlasDataLifecycleService,
    AtlasDataOnboardingService,
    DocumentExportService,
    DocumentImportService,
)
from standards_atlas.application.services.atlasdata_lifecycle_service import AtlasDataLifecycleError
from standards_atlas.application.services.atlasdata_onboarding_service import (
    AtlasDataOnboardingError,
    DoclingPartSource,
)
from standards_atlas.application.services.content_enrichment_service import ContentEnrichmentError
from standards_atlas.application.services.document_composition_service import (
    DocumentCompositionError,
)
from standards_atlas.application.services.document_selection_service import DocumentSelectionError
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import (
    atlasdata_app,
    document_app,
    document_export_app,
    doorstop_app,
    inspect_app,
)
from standards_atlas.cli.composition import (
    build_atlasdata_toc_service,
    build_content_enrichment_service,
    build_document_composition_service,
    build_document_selection_service,
    build_markdown_export_service,
)
from standards_atlas.cli.printers import print_document_summary
from standards_atlas.domain.model import DocumentKey


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
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Inspect a legacy Atlas data file through the canonical domain model."""
    reader = AtlasDataImporter()
    service = DocumentImportService(reader)
    document = service.import_document(file)
    print_document_summary(document, source_file=file, verbose=verbose)


@atlasdata_app.command("onboard-docling")
def onboard_docling(
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            resolve_path=True,
            help="Docling document.json used to discover public clause structure.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Argument(help="AtlasData file to create."),
    ],
    standard_name: Annotated[
        str,
        typer.Option("--name", help="Official standard name used in references."),
    ],
    year: Annotated[
        int,
        typer.Option("--year", help="Publication year."),
    ],
    digits: Annotated[
        int,
        typer.Option("--digits", help="AtlasData numeric identifier width."),
    ] = cli_defaults.DEFAULT_ATLASDATA_DIGITS,
    parent: Annotated[
        str | None,
        typer.Option("--parent", help="Optional AtlasData parent key."),
    ] = cli_defaults.DEFAULT_NONE,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace an existing output file."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Create an AtlasData skeleton from numbered Docling headings."""
    try:
        result = AtlasDataOnboardingService().generate(
            source,
            output,
            standard_name=standard_name,
            year=year,
            digits=digits,
            parent=parent,
            overwrite=overwrite,
        )
    except (AtlasDataOnboardingError, OSError, ValueError, json.JSONDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    term_count = sum(clause.type_marker == "t" for clause in result.clauses)
    typer.echo(f"Document source       : {source}")
    typer.echo(f"Standard              : {result.standard_name}")
    typer.echo(f"Publication year      : {result.year}")
    typer.echo(f"Clauses discovered    : {len(result.clauses)}")
    typer.echo(f"Terms discovered      : {term_count}")
    typer.echo(f"AtlasData file        : {result.output}")


@atlasdata_app.command("onboard-docling-parts")
def onboard_docling_parts(
    output: Annotated[Path, typer.Argument(help="AtlasData file to create.")],
    parts: Annotated[
        list[str],
        typer.Option(
            "--part",
            help="Explicit PART=PATH association. Repeat once per standard part.",
        ),
    ],
    standard_name: Annotated[
        str, typer.Option("--name", help="Official standard family name used in references.")
    ],
    year: Annotated[int, typer.Option("--year", help="Publication year.")],
    digits: Annotated[
        int, typer.Option("--digits", help="AtlasData numeric identifier width.")
    ] = cli_defaults.DEFAULT_ATLASDATA_DIGITS,
    parent: Annotated[
        str | None, typer.Option("--parent", help="Optional AtlasData parent key.")
    ] = cli_defaults.DEFAULT_NONE,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing output file.")
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Create one AtlasData file from explicitly assigned Docling part documents."""
    try:
        sources = tuple(DoclingPartSource.parse(value) for value in parts)
        result = AtlasDataOnboardingService().generate_parts(
            sources,
            output,
            standard_name=standard_name,
            year=year,
            digits=digits,
            parent=parent,
            overwrite=overwrite,
        )
    except (AtlasDataOnboardingError, OSError, ValueError, json.JSONDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    term_count = sum(clause.type_marker == "t" for clause in result.clauses)
    annex_count = sum(
        len(
            {
                clause.reference.split(".")[0]
                for clause in part.clauses
                if clause.reference[0].isalpha()
            }
        )
        for part in result.parts
    )
    typer.echo(f"Standard              : {result.standard_name}")
    typer.echo(f"Publication year      : {result.year}")
    typer.echo(f"Parts discovered      : {len(result.parts)}")
    for part in result.parts:
        typer.echo(f"Part {part.part:<17}: {part.source} ({len(part.clauses)} clauses)")
    typer.echo(f"Clauses discovered    : {len(result.clauses)}")
    typer.echo(f"Terms discovered      : {term_count}")
    typer.echo(f"Annexes discovered    : {annex_count}")
    typer.echo(f"AtlasData file        : {result.output}")


@atlasdata_app.command("set-status")
def set_atlasdata_status(
    file: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, writable=True, resolve_path=True),
    ],
    status: Annotated[
        AtlasDataLifecycleStatus,
        typer.Argument(help="Target lifecycle status: reviewed or published."),
    ],
) -> None:
    """Advance an AtlasData baseline through its review lifecycle."""
    try:
        result = AtlasDataLifecycleService().transition(file, status)
    except (AtlasDataLifecycleError, OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"AtlasData file        : {result.path}")
    typer.echo(f"Previous status      : {result.previous.value}")
    typer.echo(f"Lifecycle status     : {result.current.value}")


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
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Generate the TOC data section for an AtlasData file."""
    service = build_atlasdata_toc_service()
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
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


@document_app.command("derive")
def derive_document_view(
    source_key: Annotated[str, typer.Argument(help="Key of the persisted master document.")],
    target_key: Annotated[str, typer.Option("--key", help="Key for the derived document view.")],
    standard_name: Annotated[
        str,
        typer.Option("--standard", help="Exact StandardReference.standard value to select."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Create a persisted document view matching one physical source document."""
    service = build_document_selection_service(workspace)
    try:
        document = service.derive_by_standard_name(source_key, target_key, standard_name)
    except DocumentSelectionError as error:
        raise typer.BadParameter(str(error)) from error

    typer.echo(f"Source document       : {source_key}")
    typer.echo(f"Selected standard     : {standard_name}")
    typer.echo(f"Derived key           : {document.key.value}")
    typer.echo(f"Clauses               : {len(document.clauses)}")
    typer.echo(f"Persisted document    : {workspace / 'documents' / (target_key + '.json')}")


@document_app.command("derive-part")
def derive_document_part(
    source_key: Annotated[str, typer.Argument(help="Key of the persisted master document.")],
    part: Annotated[str, typer.Argument(help="AtlasData volume/part identifier.")],
    target_key: Annotated[str, typer.Option("--key", help="Key for the derived document view.")],
    title: Annotated[
        str | None, typer.Option("--title", help="Title of the derived part.")
    ] = cli_defaults.DEFAULT_NONE,
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Create a persisted document view for one AtlasData volume or standard part."""
    service = build_document_selection_service(workspace)
    try:
        document = service.derive_by_volume(source_key, target_key, part, title)
    except DocumentSelectionError as error:
        raise typer.BadParameter(str(error)) from error

    typer.echo(f"Source document       : {source_key}")
    typer.echo(f"Selected part         : {part}")
    typer.echo(f"Derived key           : {document.key.value}")
    typer.echo(f"Clauses               : {len(document.clauses)}")
    typer.echo(f"Persisted document    : {workspace / 'documents' / (target_key + '.json')}")


@document_app.command("compose-family")
def compose_family_document(
    family_key: Annotated[str, typer.Argument(help="Key of the persisted family document.")],
    part: Annotated[
        list[str] | None,
        typer.Option("--part", help="Enriched part key; repeat for every part."),
    ] = cli_defaults.DEFAULT_NONE,
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Merge enriched part documents back into their logical family document."""
    part_keys = tuple(part or ())
    if not part_keys:
        raise typer.BadParameter("At least one --part document key is required.")
    try:
        document = build_document_composition_service(workspace).compose(family_key, part_keys)
    except (DocumentCompositionError, FileNotFoundError) as error:
        raise typer.BadParameter(str(error)) from error

    enriched = sum(bool(clause.content) for clause in document.clauses)
    typer.echo(f"Family document       : {document.key.value}")
    typer.echo(f"Part documents        : {', '.join(part_keys)}")
    typer.echo(f"Clauses               : {len(document.clauses)}")
    typer.echo(f"Clauses with content  : {enriched}")


@document_app.command("enrich-content")
def enrich_document_content(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the aligned EngineeringDocument to enrich."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    automatic_alignment: Annotated[
        bool,
        typer.Option(
            "--automatic-alignment",
            help="Use alignment.json even when reviewed.json exists.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    allow_unresolved: Annotated[
        bool,
        typer.Option(
            "--allow-unresolved",
            help="Keep unresolved clauses unchanged instead of aborting.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Populate clause ContentBlocks from aligned normalized document ranges."""
    try:
        result = build_content_enrichment_service(workspace).enrich(
            document_key,
            prefer_reviewed=not automatic_alignment,
            allow_unresolved=allow_unresolved,
        )
    except (ContentEnrichmentError, OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    stats = result.statistics
    typer.echo(f"Document              : {result.document.key.value}")
    typer.echo(f"Clauses               : {stats.clauses_total}")
    typer.echo(f"Clauses enriched      : {stats.clauses_enriched}")
    typer.echo(f"Clauses empty         : {stats.clauses_empty}")
    typer.echo(f"Content blocks        : {stats.content_blocks}")
    typer.echo(f"Normalized items      : {stats.normalized_items_consumed}")
    typer.echo(
        "Alignment source      : "
        + ("reviewed.json" if stats.used_reviewed_alignment else "alignment.json")
    )
    typer.echo(f"Persisted document    : {workspace / 'documents' / (document_key + '.json')}")


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
