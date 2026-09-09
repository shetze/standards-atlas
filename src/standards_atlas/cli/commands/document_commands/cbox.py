"""Read-only inspection of the effective, accepted CBox after adoption or restore."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.atlasdata.knowledge_evidence import atomic_write
from standards_atlas.adapters.evaluation.engineering_document_clause_provider import (
    EngineeringDocumentClauseProvider,
)
from standards_atlas.application.services.cbox_report_service import CBoxReportService
from standards_atlas.cli.apps import document_app


@document_app.command("cbox-report")
def cbox_report(
    output: Annotated[
        Path, typer.Option("--output", help="Local JSON report; may contain evidence.")
    ],
    workspace: Annotated[Path, typer.Option("--workspace")] = Path(".atlas/data"),
    document: Annotated[list[str] | None, typer.Option("--document")] = None,
    clause: Annotated[list[str] | None, typer.Option("--clause")] = None,
    frame: Annotated[str, typer.Option("--frame")] = "effective-context-v1",
    knowledge_domain: Annotated[str, typer.Option("--knowledge-domain")] = "functional-safety",
    available_only: Annotated[
        bool, typer.Option("--available-only", help="Skip explicitly selected missing documents.")
    ] = False,
) -> None:
    """Render canonical CBox values, availability and sources without classification."""
    try:
        target = output.resolve()
        forbidden = (
            Path("data").resolve(),
            Path("manifests").resolve(),
            (workspace / "documents").resolve(),
            (workspace / "knowledge-evidence").resolve(),
        )
        if any(target.is_relative_to(path) for path in forbidden):
            raise ValueError("CBox report must be local, outside source and knowledge stores")
        report = CBoxReportService(EngineeringDocumentClauseProvider(workspace)).build(
            document_keys=tuple(document or ()),
            clause_ids=tuple(clause or ()),
            frame=frame,
            knowledge_domain=knowledge_domain,
            available_only=available_only,
        )
        content = (report.model_dump_json(indent=2) + "\n").encode()
        if not target.exists() or target.read_bytes() != content:
            atomic_write(target, content, private=True)
    except (OSError, KeyError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Physical documents       : {len(report.document_keys)}")
    typer.echo(f"CBox clauses             : {report.clause_count}")
    typer.echo(f"Canonical fingerprint    : {report.canonical_sha256}")
    typer.echo(f"Frame                    : {report.frame}")
    typer.echo(f"CBox report              : {output}")
    typer.echo("Read-only canonical projection. No LLM calls or public writes.")
