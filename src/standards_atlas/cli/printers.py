"""Output helpers for the Standards Atlas CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from standards_atlas.domain.model import Clause, EngineeringDocument


def print_document_summary(
    document: EngineeringDocument,
    *,
    source_file: Path | None = None,
    verbose: bool = False,
) -> None:
    """Print a human-readable summary of a Standard domain object."""
    if source_file is not None:
        typer.echo(f"File                  : {source_file.name}")

    typer.echo(f"Standard              : {document.name}")
    typer.echo(f"Key                   : {document.key.value}")

    if document.parent_key:
        typer.echo(f"Parent                : {document.parent_key.value}")

    if document.year:
        typer.echo(f"Official year         : {document.year}")

    typer.echo()
    typer.echo(f"Clauses               : {len(document.clauses)}")

    if verbose:
        typer.echo()
        typer.echo("First clauses:")
        typer.echo("-------------")

        for clause in document.clauses[:20]:
            print_clause(clause)


def print_clause(clause: Clause) -> None:
    """Print a single clause in compact CLI form."""
    title = clause.heading or ""
    volume = f" volume={clause.reference.part}" if clause.reference.part else ""
    roles = ",".join(role.value for role in clause.semantic_classification.statement_functions)
    roles_text = f" [{roles}]" if roles else ""

    typer.echo(
        f"{clause.clause_type.value:12} {clause.reference.clause:18} {title}{volume}{roles_text}"
    )
