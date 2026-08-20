"""CLI command group extracted without behavioral changes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.services import DocumentImportService
from standards_atlas.application.services.content_enrichment_service import (
    ContentEnrichmentError,
)
from standards_atlas.application.services.document_composition_service import (
    DocumentCompositionError,
)
from standards_atlas.application.services.document_selection_service import (
    DocumentSelectionError,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import document_app
from standards_atlas.cli.composition import (
    build_content_enrichment_service,
    build_document_composition_service,
    build_document_selection_service,
    build_ontology_classification_service,
    build_structural_taxonomy_service,
)


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


@document_app.command("classify-taxonomy")
def classify_document_taxonomy(
    document_key: Annotated[str, typer.Argument(help="EngineeringDocument key to classify.")],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
) -> None:
    """Materialize deterministic structural taxonomy context."""
    result = build_structural_taxonomy_service(workspace).classify(document_key)
    nodes = sum(
        clause.structural_context is not None
        and clause.structural_context.node_kind.value == "node"
        for clause in result.document.clauses
    )
    typer.echo(f"Document              : {result.document.key.value}")
    typer.echo(f"Clauses               : {len(result.document.clauses)}")
    typer.echo(f"Structural nodes      : {nodes}")
    typer.echo(f"Structural leaves     : {len(result.document.clauses) - nodes}")


@document_app.command("classify-ontology")
def classify_document_ontology(
    document_key: Annotated[str, typer.Argument(help="EngineeringDocument key to classify.")],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Standards Atlas workspace directory."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    llm_config: Annotated[
        Path | None,
        typer.Option("--llm-config", help="LLM configuration file."),
    ] = Path("cfg/llm.yaml"),
) -> None:
    """Classify semantic ontology dimensions using structural taxonomy context."""
    try:
        result = build_ontology_classification_service(
            workspace, llm_config_path=llm_config
        ).classify(document_key)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Document              : {result.document.key.value}")
    typer.echo(f"Clauses classified    : {result.clauses_classified}")
    typer.echo("Ontology profile      : semantic-profile-2.1.0")
