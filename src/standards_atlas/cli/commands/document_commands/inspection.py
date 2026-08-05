"""CLI command group extracted without behavioral changes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.application.services import DocumentImportService
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import inspect_app
from standards_atlas.cli.printers import print_document_summary


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
