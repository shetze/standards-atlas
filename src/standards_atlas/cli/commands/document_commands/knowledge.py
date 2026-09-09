"""Explicit acceptance of archived qualification results; no model execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import typer

from standards_atlas.adapters.evaluation.qualification_knowledge_source import (
    ADOPTION_DIMENSIONS,
    load_qualification_knowledge,
)
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.services.knowledge_adoption_service import KnowledgeAdoptionService
from standards_atlas.cli.apps import document_app


@document_app.command("adopt-qualification")
def adopt_qualification(
    run: Annotated[
        Path,
        typer.Option(
            "--run",
            exists=True,
            readable=True,
            help="Qualification ZIP or extracted archive with final policy artifacts.",
        ),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Canonical workspace containing documents/."),
    ] = Path(".atlas/data"),
    document: Annotated[
        list[str] | None,
        typer.Option("--document", help="Restrict to a document key; repeat as needed."),
    ] = None,
    dimension: Annotated[
        list[str] | None,
        typer.Option(
            "--dimension",
            help="Repeat: statement_functions, knowledge_kinds, "
            "applicability, role_semantics. Defaults to all four.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional local JSON change report."),
    ] = None,
    write: Annotated[
        bool,
        typer.Option("--write", help="Accept selected results into canonical documents."),
    ] = False,
    available_only: Annotated[
        bool, typer.Option("--available-only", help="Restrict selected documents to this archive.")
    ] = False,
) -> None:
    """Preview or explicitly accept selected knowledge, without LLM calls or public export."""
    try:
        if output is not None:
            target = output.resolve()
            source = run.resolve()
            documents_dir = (workspace / "documents").resolve()
            if target == source or (source.is_dir() and target.is_relative_to(source)):
                raise ValueError("adoption report cannot overwrite source archive artifacts")
            if target.is_relative_to(documents_dir):
                raise ValueError("adoption report cannot overwrite canonical documents")
        batch = load_qualification_knowledge(
            run,
            dimensions=tuple(dimension) if dimension else ADOPTION_DIMENSIONS,
        )
        service = KnowledgeAdoptionService(
            documents=FileSystemEngineeringDocumentRepository(workspace),
        )
        selected = tuple(document or ())
        if available_only and selected:
            known = {item.document_key for item in batch.candidates}
            selected = tuple(key for key in selected if key in known)
            if not selected:
                raise ValueError("selected documents have no qualified candidates in this archive")
        report = service.apply(batch, document_keys=selected, write=write)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, BadZipFile, json.JSONDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Source archive           : {report.source_id}")
    typer.echo(
        f"Selected / unqualified   : {report.selected_clause_count} / "
        f"{report.unqualified_clause_count}"
    )
    typer.echo(f"Addressed clauses        : {report.addressed_clause_count}")
    typer.echo(f"Changed documents        : {len(report.changed_document_keys)}")
    typer.echo(f"Written documents        : {len(report.written_document_keys)}")
    for status, count in report.status_counts.items():
        typer.echo(f"Attributes {status:<13}: {count}")
    if output is not None:
        typer.echo(f"Change report            : {output}")
    if not write:
        typer.echo("Dry run only. Use --write to update canonical documents.")
    typer.echo("No LLM calls. No public AtlasData export or authoritative confirmation.")
