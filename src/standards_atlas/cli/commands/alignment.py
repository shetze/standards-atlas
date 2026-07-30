"""Command-line interface for Standards Atlas."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.alignment import AlignmentArtifactRepository
from standards_atlas.application.model import AlignmentOptions
from standards_atlas.application.services import (
    AlignmentReviewService,
    AlignmentService,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import (
    align_app,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Replace an existing alignment result.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
    show_missing: Annotated[
        bool,
        typer.Option("--show-missing", help="Print missing and inferred clauses."),
    ] = cli_defaults.DEFAULT_FALSE,
    reviewed: Annotated[
        bool,
        typer.Option("--reviewed", help="Inspect reviewed.json instead of alignment.json."),
    ] = cli_defaults.DEFAULT_FALSE,
    show_conflicts: Annotated[
        bool,
        typer.Option("--show-conflicts", help="Print alignment issues."),
    ] = cli_defaults.DEFAULT_FALSE,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
    context_before: Annotated[
        int,
        typer.Option("--context-before", min=0, help="Items shown before a problem."),
    ] = cli_defaults.DEFAULT_ALIGNMENT_CONTEXT_BEFORE,
    context_after: Annotated[
        int,
        typer.Option("--context-after", min=0, help="Items shown after a problem."),
    ] = cli_defaults.DEFAULT_ALIGNMENT_CONTEXT_AFTER,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
    reset_edited: Annotated[
        bool,
        typer.Option(
            "--reset-edited",
            help="Replace the editable review with the newly generated version.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
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
    ] = cli_defaults.DEFAULT_WORKSPACE,
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
