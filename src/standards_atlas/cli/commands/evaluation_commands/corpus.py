"""Evaluation CLI command group extracted without behavioral changes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.evaluation import EngineeringDocumentClauseProvider
from standards_atlas.application.semantic_qualification.clause_access import (
    SamplingStrategy,
)
from standards_atlas.application.semantic_qualification.workflow import (
    CorpusBuildConfig,
)
from standards_atlas.application.services.evaluation import EvaluationCorpusBuilder
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("corpus-build")
def build_evaluation_corpus(
    task: Annotated[str, typer.Option("--task")],
    version: Annotated[str, typer.Option("--version")],
    count: Annotated[int, typer.Option("--count", min=1)],
    workspace: Annotated[
        Path, typer.Option("--workspace", file_okay=False)
    ] = cli_defaults.DEFAULT_WORKSPACE,
    output: Annotated[
        Path, typer.Option("--output", file_okay=False)
    ] = cli_defaults.DEFAULT_EVALUATION_CORPUS_ROOT,
    strategy: Annotated[
        SamplingStrategy, typer.Option("--strategy")
    ] = cli_defaults.DEFAULT_CORPUS_STRATEGY,
    seed: Annotated[int, typer.Option("--seed")] = cli_defaults.DEFAULT_EVALUATION_SEED,
    include_text: Annotated[
        bool, typer.Option("--include-text/--hashes-only")
    ] = cli_defaults.DEFAULT_CORPUS_INCLUDE_TEXT,
    knowledge_domain: Annotated[
        str, typer.Option("--knowledge-domain")
    ] = cli_defaults.DEFAULT_KNOWLEDGE_DOMAIN,
    corpus_id: Annotated[str | None, typer.Option("--corpus-id")] = cli_defaults.DEFAULT_NONE,
    exclude_table_dominant: Annotated[
        bool,
        typer.Option("--exclude-table-dominant/--include-table-dominant"),
    ] = True,
) -> None:
    """Create an annotation-ready corpus from persisted clauses."""
    try:
        result = EvaluationCorpusBuilder(EngineeringDocumentClauseProvider(workspace)).build(
            CorpusBuildConfig(
                task=task,
                version=version,
                count=count,
                strategy=strategy,
                seed=seed,
                include_text=include_text,
                knowledge_domain=knowledge_domain,
                corpus_id=corpus_id,
                exclude_table_dominant=exclude_table_dominant,
            ),
            output,
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Corpus clauses          : {result.clause_count}")
    typer.echo(f"Dataset                 : {result.dataset_path}")
    typer.echo(f"Manifest                : {result.manifest_path}")
