"""Evaluation CLI command group extracted without behavioral changes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.llm import (
    LlmConfig,
    OpenAICompatibleLlmGateway,
    RamaLamaServerError,
    RamaLamaServerManager,
)
from standards_atlas.application.qualification import QualificationRunReporter
from standards_atlas.application.semantic_qualification.workflow import (
    BenchmarkManifest,
)
from standards_atlas.application.services.evaluation import (
    EvaluationDatasetRepository,
    EvaluationMatrixRunner,
    EvaluationReporter,
    EvaluationRunner,
    PromptRepository,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import (
    evaluation_app,
    qualification_app,
    semantic_evaluation_app,
)


@evaluation_app.command("benchmark")
def run_evaluation_matrix(
    manifest_path: Annotated[
        Path,
        typer.Option("--manifest", exists=True, readable=True),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
) -> None:
    """Execute the prompt/model matrix declared by a benchmark manifest."""
    llm_config = LlmConfig.load(config)
    server = RamaLamaServerManager(llm_config)
    try:
        manifest = BenchmarkManifest.load(manifest_path)
        if llm_config.server.enabled and not server.status().running:
            server.start()
        result = EvaluationMatrixRunner(
            EvaluationRunner(OpenAICompatibleLlmGateway(llm_config))
        ).run(manifest)
        report_path = EvaluationReporter().write_matrix_summary(
            result.runs,
            manifest.output / "matrix-summary.json",
            manifest_hash=result.manifest_hash,
            include_case_details=manifest.include_case_details,
        )
    except (OSError, ValueError, RamaLamaServerError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    for run in result.runs:
        typer.echo(
            f"{run.prompt_version} / {run.model}: "
            f"F1={run.metrics.f1:.4f}, schema={run.metrics.schema_valid_rate:.4f}"
        )
    typer.echo(f"Matrix report           : {report_path}")
    typer.echo(f"Manifest hash           : {result.manifest_hash}")


@semantic_evaluation_app.command("run")
def run_semantic_evaluation(
    task: Annotated[str, typer.Option("--task", help="Semantic task identifier.")],
    prompt_version: Annotated[str, typer.Option("--prompt-version")],
    dataset_version: Annotated[str, typer.Option("--dataset-version")],
    model: Annotated[
        list[str] | None,
        typer.Option("--model", help="Model identifier; repeat to compare models."),
    ] = cli_defaults.DEFAULT_NONE,
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    resources: Annotated[
        Path,
        typer.Option("--resources", exists=True, file_okay=False),
    ] = cli_defaults.DEFAULT_EVALUATION_RESOURCES,
    output: Annotated[
        Path,
        typer.Option("--output", file_okay=False),
    ] = cli_defaults.DEFAULT_SEMANTIC_EVALUATION_OUTPUT,
) -> None:
    llm_config = LlmConfig.load(config)
    server = RamaLamaServerManager(llm_config)
    try:
        if llm_config.server.enabled and not server.status().running:
            server.start()
        prompt = PromptRepository(resources / "prompts").load(task, prompt_version)
        dataset = EvaluationDatasetRepository(resources / "corpora").load(task, dataset_version)
        runner = EvaluationRunner(OpenAICompatibleLlmGateway(llm_config))
        models = tuple(model or (llm_config.model,))
        runs = runner.benchmark(prompt, dataset, models)
        reporter = EvaluationReporter()
        paths = tuple(reporter.write(run, output) for run in runs)
        if len(runs) > 1:
            reporter.write_comparison(runs, output / "model-comparison.json")
    except (OSError, ValueError, RamaLamaServerError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    for run, path in zip(runs, paths, strict=True):
        typer.echo(
            f"{run.model}: F1={run.metrics.f1:.4f}, "
            f"precision={run.metrics.precision:.4f}, "
            f"recall={run.metrics.recall:.4f} -> {path}"
        )


@qualification_app.command("golden-corpus")
def qualify_golden_corpus(
    corpus: Annotated[
        Path,
        typer.Option(
            "--corpus",
            exists=True,
            file_okay=False,
            readable=True,
            resolve_path=True,
            help="Versioned golden corpus root.",
        ),
    ] = cli_defaults.DEFAULT_GOLDEN_CORPUS,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            file_okay=False,
            help="Report root; defaults to .atlas/qualification/runs.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
) -> None:
    # Resolve through the compatibility facade so existing monkeypatch and plugin hooks
    # continue to target ``standards_atlas.cli.commands.evaluation``.
    from standards_atlas.cli.commands import evaluation as evaluation_facade

    report = evaluation_facade.build_golden_corpus_qualifier().run(corpus)
    report_json, report_md = QualificationRunReporter().write(
        report,
        corpus_root=corpus,
        project_root=Path.cwd(),
        output_root=output,
    )
    typer.echo(f"Qualification status    : {'passed' if report.passed else 'failed'}")
    typer.echo(f"Cases                   : {len(report.cases)}")
    typer.echo(f"Report JSON             : {report_json}")
    typer.echo(f"Report Markdown         : {report_md}")
    if not report.passed:
        raise typer.Exit(code=1)
