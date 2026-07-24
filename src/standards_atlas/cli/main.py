"""Command-line interface for Standards Atlas."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas import __version__
from standards_atlas.adapters.alignment import AlignmentArtifactRepository
from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.adapters.atlasdata.metadata import AtlasDataLifecycleStatus
from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.adapters.docling import (
    DoclingArtifactRepository,
    DoclingJsonReader,
    DoclingNotInstalledError,
    DoclingPdfConverter,
    DocumentConversionError,
    ExtractionState,
)
from standards_atlas.adapters.doorstop import (
    AVAILABLE_DOORSTOP_TEMPLATES,
    DoorstopExportConfig,
    DoorstopExporter,
    DoorstopTemplateInstaller,
)
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.markdown import MarkdownExporter
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
from standards_atlas.application.catalog import parse_page_list
from standards_atlas.application.model import AlignmentOptions, NormalizationOptions
from standards_atlas.application.normalization import NormalizationDataLossError
from standards_atlas.application.services import (
    AlignmentReviewService,
    AlignmentService,
    AtlasDataLifecycleError,
    AtlasDataLifecycleService,
    AtlasDataOnboardingError,
    AtlasDataOnboardingService,
    ContentEnrichmentError,
    ContentEnrichmentService,
    DoclingPartSource,
    DocumentCompositionError,
    DocumentCompositionService,
    DocumentExportService,
    DocumentExtractionService,
    DocumentImportService,
    DocumentNormalizationService,
    DocumentSelectionError,
    DocumentSelectionService,
    ExtractionInspectionService,
    MarkdownExportService,
    ReferenceCandidateService,
)
from standards_atlas.application.services.atlasdata_toc_service import AtlasDataTocService
from standards_atlas.application.workflow import (
    EndToEndWorkflowService,
    WorkflowRunReporter,
)
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

align_app = typer.Typer(
    help="Align reference candidates with the AtlasData document structure.",
    no_args_is_help=True,
)
app.add_typer(align_app, name="align")

document_export_app = typer.Typer(
    help="Export persisted engineering documents.",
    no_args_is_help=True,
)

document_app.add_typer(
    document_export_app,
    name="export",
)

catalog_app = typer.Typer(
    help="Validate and inspect standard catalogs.",
    no_args_is_help=True,
)
app.add_typer(catalog_app, name="catalog")

workflow_app = typer.Typer(
    help="Plan and run catalog-driven end-to-end workflows.",
    no_args_is_help=True,
)
app.add_typer(workflow_app, name="workflow")

doorstop_app = typer.Typer(
    help="Publish internal hierarchy-based Doorstop projects.",
    no_args_is_help=True,
)
app.add_typer(doorstop_app, name="doorstop")


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
    ] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="Catalog profile key.")] = None,
    all_families: Annotated[bool, typer.Option("--all", help="Plan all catalog families.")] = False,
    hierarchy: Annotated[
        str | None, typer.Option("--hierarchy", help="Doorstop hierarchy key.")
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Plan regeneration using only supported replacement options."),
    ] = False,
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
    ] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="Catalog profile key.")] = None,
    all_families: Annotated[bool, typer.Option("--all", help="Run all catalog families.")] = False,
    hierarchy: Annotated[
        str | None, typer.Option("--hierarchy", help="Doorstop hierarchy key.")
    ] = None,
    continue_after_review: Annotated[
        bool,
        typer.Option(
            "--continue-after-review",
            help="Continue only when reviewed alignments already exist.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Regenerate reproducible artifacts using supported replacement options.",
        ),
    ] = False,
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
    ] = 8,
    parent: Annotated[
        str | None,
        typer.Option("--parent", help="Optional AtlasData parent key."),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace an existing output file."),
    ] = False,
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
    ] = 8,
    parent: Annotated[
        str | None, typer.Option("--parent", help="Optional AtlasData parent key.")
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing output file.")
    ] = False,
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
    ] = Path(".atlas"),
) -> None:
    """Create a persisted document view matching one physical source document."""
    service = DocumentSelectionService(workspace)
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
    title: Annotated[str | None, typer.Option("--title", help="Title of the derived part.")] = None,
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = Path(".atlas"),
) -> None:
    """Create a persisted document view for one AtlasData volume or standard part."""
    service = DocumentSelectionService(workspace)
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
    ] = None,
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
    ] = Path(".atlas"),
) -> None:
    """Merge enriched part documents back into their logical family document."""
    part_keys = tuple(part or ())
    if not part_keys:
        raise typer.BadParameter("At least one --part document key is required.")
    try:
        document = DocumentCompositionService(workspace).compose(family_key, part_keys)
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
    ] = Path(".atlas"),
    automatic_alignment: Annotated[
        bool,
        typer.Option(
            "--automatic-alignment",
            help="Use alignment.json even when reviewed.json exists.",
        ),
    ] = False,
    allow_unresolved: Annotated[
        bool,
        typer.Option(
            "--allow-unresolved",
            help="Keep unresolved clauses unchanged instead of aborting.",
        ),
    ] = False,
) -> None:
    """Populate clause ContentBlocks from aligned normalized document ranges."""
    try:
        result = ContentEnrichmentService(workspace).enrich(
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
    ] = Path(".atlas"),
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
    ] = None,
    replace_existing: Annotated[
        bool,
        typer.Option("--replace/--no-replace", help="Replace existing Markdown files."),
    ] = True,
) -> None:
    """Export one standard family to one Markdown file per physical part."""
    export_target = target if target is not None else Path("local/exports/markdown") / document_key
    service = MarkdownExportService(MarkdownExporter(), workspace=workspace)
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
    parent: Annotated[
        str | None,
        typer.Option(
            "--parent",
            help="Doorstop parent document prefix derived from the catalog hierarchy.",
        ),
    ] = None,
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
    ] = Path(".atlas"),
    local_root: Annotated[
        Path, typer.Option("--local-root", help="Root for local consumable outputs.")
    ] = Path("local"),
    replace_existing: Annotated[
        bool, typer.Option("--replace/--no-replace", help="Replace published output.")
    ] = True,
    template: Annotated[
        str,
        typer.Option(
            "--template",
            help="Packaged Standards Atlas Doorstop template.",
        ),
    ] = "atlas-clean",
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


def _parse_page_range(value: str) -> tuple[int, int | None]:
    try:
        start_text, end_text = value.split(":", maxsplit=1)
        start = int(start_text)
        end = int(end_text) if end_text else None
    except ValueError as exc:
        raise ValueError(f"Invalid page range {value!r}; expected START:END or START:") from exc
    if start < 1 or (end is not None and end < start):
        raise ValueError(f"Invalid page range {value!r}")
    return start, end


@normalize_app.command("run")
def normalize_extracted_document(
    document_key: Annotated[str, typer.Argument(help="Key of a persisted Docling document.")],
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
    ] = Path(".atlas"),
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing normalized document.")
    ] = False,
    page_range: Annotated[
        list[str] | None,
        typer.Option(
            "--page-range",
            help="Inclusive positive one-based page range START:END; repeat for multiple ranges.",
        ),
    ] = None,
    exclude_page_range: Annotated[
        list[str] | None,
        typer.Option(
            "--exclude-page-range",
            help="Inclusive one-based page range to exclude; repeat for multiple ranges.",
        ),
    ] = None,
    page_list: Annotated[
        str | None,
        typer.Option(
            "--page-list",
            help="Positive comma-separated pages and ranges, for example 1,3,5,11-13,15.",
        ),
    ] = None,
) -> None:
    """Normalize an extracted document and persist the result below .atlas."""
    repository = NormalizationArtifactRepository(workspace)
    target = repository.document_path(document_key)
    if target.exists() and not overwrite:
        typer.echo("A normalized document already exists. Use --overwrite to replace it.", err=True)
        raise typer.Exit(code=3)
    try:
        page_ranges = tuple(_parse_page_range(value) for value in (page_range or ()))
        excluded_ranges = tuple(_parse_page_range(value) for value in (exclude_page_range or ()))
        selected_pages = parse_page_list(page_list) if page_list else ()
        result = DocumentNormalizationService(workspace=workspace).normalize(
            document_key,
            options=NormalizationOptions(
                page_ranges=page_ranges,
                exclude_page_ranges=excluded_ranges,
                page_list=selected_pages,
            ),
        )
    except (NormalizationDataLossError, OSError, ValueError) as exc:
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
    typer.echo(f"Active source items         : {stats.active_source_items}")
    typer.echo(f"Suppressed source items     : {stats.suppressed_source_items}")
    typer.echo(f"Unaccounted source items    : {stats.unaccounted_source_items}")
    typer.echo(f"Duplicate source items      : {stats.duplicate_source_items}")
    typer.echo(f"Source pages                : {stats.source_pages}")
    options = result.metadata.options
    if options.page_ranges:
        rendered_ranges = ", ".join(
            f"{start}-{end if end is not None else 'end'}" for start, end in options.page_ranges
        )
        typer.echo(f"Selected page ranges        : {rendered_ranges}")
    if options.page_list:
        typer.echo(
            "Selected page list          : " + ",".join(str(page) for page in options.page_list)
        )
    if options.exclude_page_ranges:
        rendered_exclusions = ", ".join(
            f"{start}-{end if end is not None else 'end'}"
            for start, end in options.exclude_page_ranges
        )
        typer.echo(f"Excluded page ranges        : {rendered_exclusions}")
    if options.page_ranges or options.page_list or options.exclude_page_ranges:
        typer.echo(f"Pages included              : {stats.selected_pages}")
        typer.echo(f"Pages excluded              : {stats.excluded_pages}")
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
    typer.echo(f"Active source items         : {stats.active_source_items}")
    typer.echo(f"Suppressed source items     : {stats.suppressed_source_items}")
    typer.echo(f"Unaccounted source items    : {stats.unaccounted_source_items}")
    typer.echo(f"Duplicate source items      : {stats.duplicate_source_items}")


@reference_app.command("detect")
def detect_reference_candidates(
    document_key: Annotated[
        str,
        typer.Argument(
            help="Key of the normalized and engineering document.",
        ),
    ],
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", help="Standards Atlas workspace directory.")
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
                    f"{candidate.normalized_reference:12} "
                    f"{candidate.title_remainder or candidate.following_label or ''}"
                )


@align_app.command("run")
def run_alignment(
    document_key: Annotated[
        str,
        typer.Argument(
            help="Key shared by the engineering, normalized and candidate documents.",
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
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Replace an existing alignment result.",
        ),
    ] = False,
) -> None:
    """Align reference candidates monotonically with AtlasData clauses."""
    repository = AlignmentArtifactRepository(workspace)
    target = repository.document_path(document_key)
    if target.exists() and not overwrite:
        typer.echo(
            "An alignment result already exists. Use --overwrite to replace it.",
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        result = AlignmentService(workspace).run(
            document_key,
            AlignmentOptions(),
        )
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source       : {result.source_id}")
    typer.echo(f"Expected clauses      : {stats.expected_clauses}")
    typer.echo(f"Exact matches         : {stats.exact_matches}")
    typer.echo(f"Normalized matches    : {stats.normalized_matches}")
    typer.echo(f"Annex matches         : {stats.annex_matches}")
    typer.echo(f"Low-confidence       : {stats.low_confidence_matches}")
    typer.echo(f"Inferred matches      : {stats.inferred_matches}")
    typer.echo(f"Missing               : {stats.missing}")
    typer.echo(f"Conflicting           : {stats.conflicting}")
    typer.echo(f"Unassigned ranges     : {stats.unassigned_ranges}")
    typer.echo(f"Alignment document    : {target}")


@align_app.command("inspect")
def inspect_alignment(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of a persisted alignment result."),
    ],
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            "-w",
            help="Standards Atlas workspace directory.",
        ),
    ] = Path(".atlas"),
    show_missing: Annotated[
        bool,
        typer.Option("--show-missing", help="Print missing and inferred clauses."),
    ] = False,
    reviewed: Annotated[
        bool,
        typer.Option("--reviewed", help="Inspect reviewed.json instead of alignment.json."),
    ] = False,
    show_conflicts: Annotated[
        bool,
        typer.Option("--show-conflicts", help="Print alignment issues."),
    ] = False,
) -> None:
    """Inspect a persisted alignment result."""
    try:
        result = (
            AlignmentReviewService(workspace).load_reviewed(document_key)
            if reviewed
            else AlignmentService(workspace).load(document_key)
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source       : {result.source_id}")
    typer.echo(f"Expected clauses      : {stats.expected_clauses}")
    typer.echo(f"Exact matches         : {stats.exact_matches}")
    typer.echo(f"Normalized matches    : {stats.normalized_matches}")
    typer.echo(f"Annex matches         : {stats.annex_matches}")
    typer.echo(f"Low-confidence       : {stats.low_confidence_matches}")
    typer.echo(f"Inferred matches      : {stats.inferred_matches}")
    typer.echo(f"Missing               : {stats.missing}")
    typer.echo(f"Unassigned ranges     : {stats.unassigned_ranges}")
    typer.echo(f"Issues                : {len(result.issues)}")
    if show_missing:
        for clause in result.clauses:
            if clause.status.value in {"missing", "low_confidence", "sequence_inferred"}:
                typer.echo(
                    f"{clause.status.value:18} {clause.expected_reference:12} {clause.clause_id}"
                )
    if show_conflicts:
        for issue in result.issues:
            if issue.severity in {"warning", "error"}:
                typer.echo(f"{issue.severity:7} {issue.code:28} {issue.message}")


@align_app.command("review")
def generate_alignment_review(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the automatic alignment to review."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = Path(".atlas"),
    context_before: Annotated[
        int,
        typer.Option("--context-before", min=0, help="Items shown before a problem."),
    ] = 2,
    context_after: Annotated[
        int,
        typer.Option("--context-after", min=0, help="Items shown after a problem."),
    ] = 4,
) -> None:
    """Generate Markdown review context and an override YAML template."""
    try:
        review_path, overrides_path = AlignmentReviewService(workspace).generate_review(
            document_key,
            context_before=context_before,
            context_after=context_after,
        )
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Review document       : {review_path}")
    typer.echo(f"Override document     : {overrides_path}")


@align_app.command("review-export")
def export_full_alignment_review(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the automatic alignment to export for review."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = Path(".atlas"),
    reset_edited: Annotated[
        bool,
        typer.Option(
            "--reset-edited",
            help="Replace the editable review with the newly generated version.",
        ),
    ] = False,
) -> None:
    """Export the complete normalized document as editable review Markdown."""
    try:
        generated, edited = AlignmentReviewService(workspace).export_full_document_review(
            document_key,
            reset_edited=reset_edited,
        )
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Generated review      : {generated}")
    typer.echo(f"Editable review       : {edited}")


@align_app.command("review-validate")
def validate_full_alignment_review(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the edited full-document review."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = Path(".atlas"),
) -> None:
    """Validate that the edited review changes alignment markers only."""
    try:
        diff = AlignmentReviewService(workspace).validate_full_document_review(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Alignment changes     : {len(diff.changes)}")
    typer.echo("Reviewed Markdown is valid.")


@align_app.command("review-diff")
def diff_full_alignment_review(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the edited full-document review."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = Path(".atlas"),
) -> None:
    """Show structural changes made in the editable review Markdown."""
    try:
        diff = AlignmentReviewService(workspace).diff_full_document_review(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    counts: dict[str, int] = {}
    for change in diff.changes:
        counts[change.kind.value] = counts.get(change.kind.value, 0) + 1
    for kind, count in sorted(counts.items()):
        typer.echo(f"{kind:22}: {count}")
    if not counts:
        typer.echo("No review changes detected.")


@align_app.command("review-import")
def import_full_alignment_review(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the edited full-document review."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = Path(".atlas"),
) -> None:
    """Translate edited Markdown alignment markers into overrides.yaml."""
    try:
        path = AlignmentReviewService(workspace).import_full_document_review(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Override document     : {path}")


@align_app.command("validate-overrides")
def validate_alignment_overrides(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the alignment override document."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = Path(".atlas"),
) -> None:
    """Validate manual alignment decisions without applying them."""
    try:
        result = AlignmentReviewService(workspace).validate_overrides(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    if result.valid:
        typer.echo("Alignment overrides are valid.")
        return
    for issue in result.issues:
        typer.echo(f"{issue.severity:7} {issue.code:30} {issue.message}")
    raise typer.Exit(code=2)


@align_app.command("review-apply")
def apply_alignment_overrides(
    document_key: Annotated[
        str,
        typer.Argument(help="Key of the alignment override document."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = Path(".atlas"),
) -> None:
    """Apply validated overrides and persist reviewed.json."""
    service = AlignmentReviewService(workspace)
    try:
        result = service.apply_overrides(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    stats = result.metadata.statistics
    typer.echo(f"Document source       : {result.source_id}")
    typer.echo(f"Missing               : {stats.missing}")
    typer.echo(f"Low-confidence       : {stats.low_confidence_matches}")
    typer.echo(f"Inferred matches      : {stats.inferred_matches}")
    typer.echo(f"Reviewed alignment    : {service.reviewed_path(document_key)}")


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
