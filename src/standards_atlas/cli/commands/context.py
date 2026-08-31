"""Read-only context discovery commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import context_app
from standards_atlas.cli.composition import build_subject_candidate_vocabulary_service


@context_app.command("subject-vocabulary")
def subject_vocabulary(
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            file_okay=False,
            help="Engineering-document workspace to inspect.",
        ),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            dir_okay=False,
            help="Write the complete subject-candidate vocabulary as JSON.",
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            min=0,
            help="Maximum number of frequent candidates to show; 0 shows none.",
        ),
    ] = 20,
) -> None:
    """Discover subject candidates from persisted AtlasData term headings."""
    vocabulary = build_subject_candidate_vocabulary_service(workspace).build()
    analysis = vocabulary.analysis

    typer.echo(f"Term clauses              : {analysis.term_clauses}")
    typer.echo(f"Accepted term clauses     : {analysis.accepted_term_clauses}")
    typer.echo(f"Ignored term containers   : {analysis.ignored_term_containers}")
    typer.echo(f"Missing term headings     : {analysis.missing_headings}")
    typer.echo(f"Unique candidates         : {analysis.unique_candidates}")
    typer.echo(f"Repeated candidates       : {analysis.repeated_candidates}")
    typer.echo(f"Cross-document candidates : {analysis.cross_document_candidates}")
    typer.echo(f"Extraction coverage       : {analysis.extraction_coverage:.1%}")

    if limit:
        ranked = sorted(
            vocabulary.candidates,
            key=lambda candidate: (
                -len(candidate.provenance),
                candidate.normalized_label,
            ),
        )[:limit]
        if ranked:
            typer.echo("\nMost frequent candidates")
            for candidate in ranked:
                typer.echo(
                    f"{len(candidate.provenance):>5}  "
                    f"{candidate.document_count:>3} docs  "
                    f"{candidate.normalized_label}"
                )

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(vocabulary.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        typer.echo(f"\nVocabulary JSON           : {output}")
