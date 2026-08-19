"""Challenger qualification CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.application.semantic_qualification.challenger import (
    load_hard_case_selection,
    write_challenger_manifest,
    write_hard_case_selection,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.cli.commands.evaluation_commands.qualification_matrix import (
    qualify_model_prompt_matrix,
)


@evaluation_app.command("challenger-qualification")
def qualify_challengers(
    manifest_path: Annotated[Path, typer.Option("--manifest", exists=True, readable=True)],
    output_directory: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "local/evaluation/challenger"
    ),
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh/--allow-reuse",
            help="Use fresh provider inference by default; allow cached/reused data explicitly.",
        ),
    ] = True,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    sample: Annotated[
        str | None,
        typer.Option(
            "--sample",
            help="Use a named hard-case sample, currently: applicability-conflicts.",
        ),
    ] = None,
    sample_from: Annotated[
        Path | None,
        typer.Option(
            "--sample-from",
            exists=True,
            readable=True,
            help="Qualification-run ZIP used to derive the hard-case sample.",
        ),
    ] = None,
) -> None:
    """Qualify configured challenger models head-to-head without changing the cascade."""
    source = QualificationMatrixManifest.load(manifest_path)
    if (sample is None) != (sample_from is None):
        raise typer.BadParameter("--sample and --sample-from must be provided together")
    selected_example_ids = None
    run_directory = output_directory / f"{source.matrix_id}-challengers"
    sample_selection_path = run_directory / "challenger-sample-selection.json"
    if sample is None and sample_selection_path.exists():
        sample_selection_path.unlink()
    sample_selection_path = None
    if sample is not None and sample_from is not None:
        selected_example_ids, selection = load_hard_case_selection(
            source_manifest=source, run_archive=sample_from, sample=sample
        )
        if limit is not None:
            selected_example_ids = selected_example_ids[:limit]
            selection = {
                **selection,
                "clause_count": len(selected_example_ids),
                "clause_ids": list(selected_example_ids),
                "limit": limit,
            }
        sample_selection_path = write_hard_case_selection(
            selection=selection, path=run_directory / "challenger-sample-selection.json"
        )
        typer.echo(f"Challenger sample         : {sample} ({len(selected_example_ids)} clauses)")
    derived_path = output_directory / "challenger-manifest.yaml"
    write_challenger_manifest(manifest=source, path=derived_path)
    derived = QualificationMatrixManifest.load(derived_path)

    qualify_model_prompt_matrix(
        manifest_path=derived_path,
        output_directory=output_directory,
        fresh=fresh,
        fail_on_matrix_failure=False,
        limit=None if selected_example_ids is not None else limit,
        challenger_source_manifest=manifest_path,
        selected_example_ids_override=(
            list(selected_example_ids) if selected_example_ids is not None else None
        ),
        challenger_sample_path=sample_selection_path,
    )
    run_directory = output_directory / derived.matrix_id
    typer.echo(f"Challenger JSON          : {run_directory / 'challenger-comparison.json'}")
    typer.echo(f"Challenger report        : {run_directory / 'challenger-comparison.md'}")
