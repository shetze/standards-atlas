"""CLI command group extracted without behavioral changes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.atlasdata.metadata import AtlasDataLifecycleStatus
from standards_atlas.adapters.atlasdata.semantic_annotation_writer import (
    AtlasDataSemanticAnnotationService,
)
from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.application.services import (
    AtlasDataLifecycleService,
    AtlasDataOnboardingService,
)
from standards_atlas.application.services.atlasdata_lifecycle_service import (
    AtlasDataLifecycleError,
)
from standards_atlas.application.services.atlasdata_onboarding_service import (
    AtlasDataOnboardingError,
    DoclingPartSource,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import atlasdata_app
from standards_atlas.cli.composition import build_atlasdata_toc_service


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


@atlasdata_app.command("onboard-family")
def onboard_family(
    family_key: Annotated[
        str,
        typer.Argument(help="Standard family key declared in the standards manifest."),
    ],
    manifest: Annotated[
        Path,
        typer.Option(
            "--manifest",
            exists=True,
            readable=True,
            resolve_path=True,
            help="Standards manifest declaring the family and its physical parts.",
        ),
    ] = Path("manifests/standards.yaml"),
    docling_root: Annotated[
        Path,
        typer.Option(
            "--docling-root",
            help="Root containing <document-key>/document.json Docling artifacts.",
        ),
    ] = Path(".atlas/data/docling"),
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            help="AtlasData file to create; defaults to local/proposed/<family>.",
        ),
    ] = None,
    digits: Annotated[
        int, typer.Option("--digits", help="AtlasData numeric identifier width.")
    ] = cli_defaults.DEFAULT_ATLASDATA_DIGITS,
    parent: Annotated[
        str | None, typer.Option("--parent", help="Optional AtlasData parent key.")
    ] = cli_defaults.DEFAULT_NONE,
    include_supplements: Annotated[
        bool,
        typer.Option(
            "--include-supplements",
            help="Include manifest-declared supplements as part-supplement sources.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing proposed output file.")
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Create one AtlasData family file from manifest-declared Docling artifacts."""
    try:
        catalog = YamlStandardCatalogReader().read(manifest)
        family = catalog.family(family_key)
        target = output or Path("local/proposed") / family.key
        result = AtlasDataOnboardingService().generate_family(
            family,
            target,
            docling_root=docling_root,
            digits=digits,
            parent=parent,
            overwrite=overwrite,
            include_supplements=include_supplements,
        )
    except (
        AtlasDataOnboardingError,
        KeyError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    term_count = sum(clause.type_marker == "t" for clause in result.clauses)
    table_count = sum(len(part.tables) for part in result.parts)
    typer.echo(f"Family                : {family.key}")
    typer.echo(f"Standard              : {result.standard_name}")
    typer.echo(f"Parts discovered      : {len(result.parts)}")
    for part in result.parts:
        typer.echo(
            f"Part {part.part:<17}: {part.source} "
            f"({part.publication_year}; {len(part.clauses)} clauses; {len(part.tables)} tables)"
        )
    typer.echo(f"Clauses discovered    : {len(result.clauses)}")
    typer.echo(f"Terms discovered      : {term_count}")
    typer.echo(f"Tables discovered     : {table_count}")
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


@atlasdata_app.command("apply-semantic-annotations")
def apply_semantic_annotations(
    file: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, resolve_path=True),
    ],
    annotations: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, resolve_path=True),
    ],
    write: Annotated[
        bool,
        typer.Option("--write", help="Write semantic annotations to the AtlasData file."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Apply reviewed, publishable semantic annotations to TOC records."""
    try:
        result = AtlasDataSemanticAnnotationService().apply(file, annotations, write=write)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"File                  : {result.source.name}")
    typer.echo(f"Semantic profile      : {result.semantic_profile}")
    typer.echo(f"Updated TOC records   : {result.updated_records}")
    typer.echo(f"Unchanged TOC records : {result.unchanged_records}")
    typer.echo(f"Changed               : {result.changed}")
    if write and result.backup:
        typer.echo(f"Backup                : {result.backup.name}")
    elif not write:
        typer.echo("Dry run only. Use --write to update the file.")
