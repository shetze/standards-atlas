"""Output helpers for the Standards Atlas CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from standards_atlas.domain.model import Clause, Standard


def print_standard_summary(
    standard: Standard,
    *,
    source_file: Path | None = None,
    verbose: bool = False,
) -> None:
    """Print a human-readable summary of a Standard domain object."""
    if source_file is not None:
        typer.echo(f"File                  : {source_file.name}")

    typer.echo(f"Standard              : {standard.name}")
    typer.echo(f"Key                   : {standard.key.value}")

    if standard.parent_key:
        typer.echo(f"Parent                : {standard.parent_key.value}")

    if standard.year:
        typer.echo(f"Official year         : {standard.year}")

    typer.echo()
    typer.echo(f"Clauses               : {len(standard.clauses)}")

    if verbose:
        typer.echo()
        typer.echo("First clauses:")
        typer.echo("-------------")

        for clause in standard.clauses[:20]:
            print_clause(clause)


def print_clause(clause: Clause) -> None:
    """Print a single clause in compact CLI form."""
    title = clause.title or ""
    volume = f" volume={clause.volume}" if clause.volume else ""
    roles = ",".join(role.value for role in clause.semantic_roles)
    roles_text = f" [{roles}]" if roles else ""

    typer.echo(
        f"{clause.clause_type.value:12} "
        f"{clause.reference.clause:18} "
        f"{title}{volume}{roles_text}"
    )
