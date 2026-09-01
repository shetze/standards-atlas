"""Evaluation CLI command group extracted without behavioral changes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.evaluation import EngineeringDocumentClauseProvider
from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
    build_applicability_golden_review,
    evaluate_applicability_golden_corpus,
    publish_applicability_golden_review,
)
from standards_atlas.application.semantic_qualification.applicability_hard_cases import (
    analyze_applicability_hard_cases,
)
from standards_atlas.application.semantic_qualification.clause_access import (
    SamplingStrategy,
)
from standards_atlas.application.semantic_qualification.role_corpus import (
    RoleCorpusBuildManifest,
    RoleGoldenCorpus,
    RoleGoldenCorpusBuilder,
    evaluate_role_golden_corpus,
    publish_role_golden_review,
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
    exclude_context_meta: Annotated[
        bool,
        typer.Option(
            "--exclude-context-meta/--include-context-meta",
            help=(
                "Exclude scope declarations and reference-section routing metadata from "
                "clause-semantic qualification corpora."
            ),
        ),
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
                exclude_context_meta=exclude_context_meta,
            ),
            output,
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Corpus clauses          : {result.clause_count}")
    typer.echo(f"Dataset                 : {result.dataset_path}")
    typer.echo(f"Manifest                : {result.manifest_path}")


@evaluation_app.command("role-corpus-build")
def build_role_golden_corpus(
    manifest: Annotated[Path, typer.Option("--manifest", exists=True, dir_okay=False)],
    workspace: Annotated[
        Path, typer.Option("--workspace", file_okay=False)
    ] = cli_defaults.DEFAULT_WORKSPACE,
    output: Annotated[
        Path, typer.Option("--output", file_okay=False)
    ] = cli_defaults.DEFAULT_EVALUATION_CORPUS_ROOT,
    review_output: Annotated[
        Path, typer.Option("--review-output", file_okay=False)
    ] = cli_defaults.DEFAULT_REVIEW_ROOT,
) -> None:
    """Build deterministic role candidates and a flat HITL review CSV."""
    try:
        config = RoleCorpusBuildManifest.load(manifest)
        result = RoleGoldenCorpusBuilder(EngineeringDocumentClauseProvider(workspace)).build(
            config, output, review_output
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Role corpus clauses     : {result.selected_count}")
    typer.echo(f"Dataset                 : {result.dataset_path}")
    typer.echo(f"HITL review file        : {result.review_path}")
    typer.echo(f"HITL review guide       : {result.review_guide_path}")
    if result.review_created:
        typer.echo("                          EDIT THIS CSV FILE")
    else:
        typer.echo("                          existing review preserved")
    typer.echo(f"Manifest                : {result.manifest_path}")
    if result.shortfalls:
        typer.echo(f"Quota shortfalls        : {result.shortfalls}")


@evaluation_app.command("role-corpus-publish")
def publish_role_corpus(
    review: Annotated[Path, typer.Option("--review", exists=True, dir_okay=False)],
    manifest: Annotated[Path, typer.Option("--manifest", exists=True, dir_okay=False)],
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False)] = None,
) -> None:
    """Compile reviewed CSV rows into a machine-readable golden corpus."""
    resolved_output = output or manifest.parent / "role-golden-corpus.yaml"
    try:
        corpus = publish_role_golden_review(review, manifest, resolved_output)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Published gold cases    : {len(corpus.cases)}")
    typer.echo(f"Golden corpus           : {resolved_output}")


@evaluation_app.command("role-corpus-evaluate")
def evaluate_role_corpus(
    golden: Annotated[Path, typer.Option("--golden", exists=True, dir_okay=False)],
    consensus: Annotated[Path, typer.Option("--consensus", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Evaluate role presence and relation tuples against published golden cases."""
    import json

    try:
        corpus = RoleGoldenCorpus.load(golden)
        payload = json.loads(consensus.read_text(encoding="utf-8"))
        report = evaluate_role_golden_corpus(corpus, payload)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Published gold cases    : {report.published_cases}")
    typer.echo(f"Presence F1             : {report.presence_f1:.3f}")
    typer.echo(f"Tuple F1                : {report.tuple_f1:.3f}")
    typer.echo(f"Report                  : {output}")


@evaluation_app.command("applicability-hard-cases")
def analyze_applicability_presence_hard_cases(
    run_archive: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "local/evaluation/applicability-hard-cases"
    ),
    limit: Annotated[int, typer.Option("--limit", min=1, max=500)] = 30,
) -> None:
    """Rank applicability presence disagreements from an immutable qualification run."""
    try:
        report, artifacts = analyze_applicability_hard_cases(run_archive, output, limit=limit)
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Analyzed clauses         : {report.analyzed_clauses}")
    typer.echo(
        "Balanced disagreements   : "
        f"{report.category_counts.get('balanced_presence_disagreement', 0)}"
    )
    typer.echo(
        "Minority disagreements   : "
        f"{report.category_counts.get('minority_presence_disagreement', 0)}"
    )
    typer.echo(f"Review candidates        : {artifacts.selected_count}")
    typer.echo(f"JSON report              : {artifacts.json_path}")
    typer.echo(f"Markdown report          : {artifacts.markdown_path}")
    typer.echo(f"HITL review CSV          : {artifacts.review_path}")


@evaluation_app.command("applicability-corpus-build")
def build_applicability_golden_corpus(
    run_archive: Annotated[Path, typer.Option("--run", exists=True, dir_okay=False)],
    review_output: Annotated[
        Path, typer.Option("--review-output", file_okay=False)
    ] = cli_defaults.DEFAULT_REVIEW_ROOT,
    golden: Annotated[Path | None, typer.Option("--golden", exists=True, dir_okay=False)] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 30,
) -> None:
    """Build an incremental stratified HITL set for applicability qualification."""
    try:
        result = build_applicability_golden_review(
            run_archive, review_output, golden_path=golden, limit=limit
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Applicability candidates: {result.candidate_count}")
    typer.echo(f"Already in golden corpus: {result.excluded_existing_count}")
    typer.echo(f"Selected for review     : {result.selected_count}")
    for category, count in result.category_selected_counts.items():
        available = result.category_candidate_counts.get(category, 0)
        typer.echo(f"  {category:<28}: {count} / {available}")
    typer.echo(f"Documents represented   : {result.document_count}")
    typer.echo(f"HITL review file        : {result.review_path}")
    typer.echo(f"HITL review guide       : {result.review_guide_path}")
    if result.review_created:
        typer.echo("                          EDIT THIS CSV FILE")
    else:
        typer.echo("                          existing review preserved")


@evaluation_app.command("applicability-corpus-publish")
def publish_applicability_corpus(
    review: Annotated[Path, typer.Option("--review", exists=True, dir_okay=False)],
    run_archive: Annotated[Path, typer.Option("--run", exists=True, dir_okay=False)],
    golden: Annotated[Path | None, typer.Option("--golden", exists=True, dir_okay=False)] = None,
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False)] = None,
) -> None:
    """Publish reviewed applicability cases, optionally merging an existing golden corpus."""
    resolved_output = output or review.parent / "applicability-golden-corpus.yaml"
    try:
        corpus = publish_applicability_golden_review(
            review, run_archive, resolved_output, golden_path=golden
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Published gold cases    : {len(corpus.cases)}")
    typer.echo(f"Golden corpus           : {resolved_output}")


@evaluation_app.command("applicability-corpus-evaluate")
def evaluate_applicability_corpus(
    golden: Annotated[Path, typer.Option("--golden", exists=True, dir_okay=False)],
    run_archive: Annotated[Path, typer.Option("--run", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Evaluate applicability consensus and individual models against HITL gold."""
    try:
        corpus = ApplicabilityGoldenCorpus.load(golden)
        report = evaluate_applicability_golden_corpus(corpus, run_archive)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Published gold cases    : {report.published_cases}")
    typer.echo(
        f"Published class balance : {report.positive_cases} positive / "
        f"{report.negative_cases} negative"
    )
    typer.echo(f"Baseline majority F1    : {report.baseline_majority.presence_f1:.3f}")
    typer.echo(f"Model metrics           : {len(report.models)}")
    typer.echo(f"Offline ensembles       : {len(report.ensembles)}")
    typer.echo(f"Presence errors         : {len(report.errors)}")
    typer.echo(f"Report                  : {output}")
