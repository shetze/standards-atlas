"""Command-line interface for Standards Atlas."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.docling import (
    DoclingArtifactRepository,
    DoclingJsonReader,
    DoclingNotInstalledError,
    DoclingPdfConverter,
    DocumentConversionError,
    ExtractionState,
)
from standards_atlas.adapters.llm import (
    RamaLamaServerError,
)
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
from standards_atlas.application.catalog import parse_page_list
from standards_atlas.application.model import NormalizationOptions
from standards_atlas.application.normalization import NormalizationDataLossError
from standards_atlas.application.services import (
    DocumentExtractionService,
    ExtractionInspectionService,
    ReferenceCandidateService,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import (
    docling_app,
    normalize_app,
    reference_app,
)
from standards_atlas.cli.composition import build_document_normalization_service
from standards_atlas.cli.runtime_managers import managed_llm_server


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
    ] = cli_defaults.DEFAULT_WORKSPACE,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace an existing native Docling document."),
    ] = cli_defaults.DEFAULT_FALSE,
    llm_config: Annotated[
        Path,
        typer.Option(
            "--llm-config",
            exists=True,
            readable=True,
            help="Managed LLM configuration used to release the GPU during conversion.",
        ),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
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
        server = managed_llm_server(llm_config)
        with server.stopped_for_exclusive_accelerator():
            generated = service.convert(file, target, overwrite=overwrite)
        repository.save_metadata(document_key, converter.conversion_metadata(file))
    except (
        DoclingNotInstalledError,
        DocumentConversionError,
        FileExistsError,
        RamaLamaServerError,
        ValueError,
    ) as exc:
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing normalized document.")
    ] = cli_defaults.DEFAULT_FALSE,
    page_range: Annotated[
        list[str] | None,
        typer.Option(
            "--page-range",
            help="Inclusive positive one-based page range START:END; repeat for multiple ranges.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
    exclude_page_range: Annotated[
        list[str] | None,
        typer.Option(
            "--exclude-page-range",
            help="Inclusive one-based page range to exclude; repeat for multiple ranges.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
    page_list: Annotated[
        str | None,
        typer.Option(
            "--page-list",
            help="Positive comma-separated pages and ranges, for example 1,3,5,11-13,15.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
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
        result = build_document_normalization_service(workspace).normalize(
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
    show_unexpected: Annotated[
        bool, typer.Option("--show-unexpected", help="Print unexpected and ambiguous candidates.")
    ] = cli_defaults.DEFAULT_FALSE,
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
