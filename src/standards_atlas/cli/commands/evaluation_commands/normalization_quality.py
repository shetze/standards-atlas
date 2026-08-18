"""CLI for exploratory normalization-quality model qualification."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.llm import (
    LlmConfig,
    OpenAICompatibleLlmGateway,
    RamaLamaServerError,
    RamaLamaServerManager,
)
from standards_atlas.application.normalization_quality import (
    NormalizationQualityReporter,
    NormalizationQualityRunner,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import evaluation_app

DEFAULT_MODELS = (
    "mistral-small-3.2-24b-instruct-q4-k-m",
    "gemma-3-12b-it-q4-k-m",
)


@evaluation_app.command("normalization-quality")
def qualify_normalization_quality(
    corpus: Annotated[
        Path,
        typer.Option(
            "--corpus",
            exists=True,
            readable=True,
            dir_okay=False,
            help="Existing evaluation corpus dataset.json; semantic labels are ignored.",
        ),
    ],
    manifest_path: Annotated[
        Path,
        typer.Option(
            "--manifest",
            exists=True,
            readable=True,
            dir_okay=False,
            help="Qualification manifest used only to resolve configured model definitions.",
        ),
    ],
    model: Annotated[
        list[str] | None,
        typer.Option(
            "--model",
            help=(
                "Configured model id; repeat to compare models. Defaults to Mistral Small "
                "3.2 24B and Gemma 3 12B when both are present in the manifest."
            ),
        ),
    ] = None,
    config: Annotated[
        Path, typer.Option("--config", exists=True, readable=True)
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    resources: Annotated[Path, typer.Option("--resources", exists=True, file_okay=False)] = Path(
        "src/standards_atlas/resources/normalization"
    ),
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "local/evaluation/normalization-quality"
    ),
    limit: Annotated[
        int | None, typer.Option("--limit", min=1, help="Limit clauses for a trial run.")
    ] = None,
    max_tokens: Annotated[
        int | None,
        typer.Option(
            "--max-tokens",
            min=1,
            help="Override the model-specific structured output token budget.",
        ),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Bypass the shared LLM response cache."),
    ] = False,
) -> None:
    """Compare configured local models as read-only normalization-quality reviewers."""
    base_config = LlmConfig.load(config)
    active_server: RamaLamaServerManager | None = None
    try:
        manifest = QualificationMatrixManifest.load(manifest_path)
        model_by_id = {candidate.id: candidate for candidate in manifest.models}
        selected_ids = tuple(model or _default_model_ids(model_by_id))
        unknown = [model_id for model_id in selected_ids if model_id not in model_by_id]
        if unknown:
            raise ValueError(f"unknown model ids in --model: {unknown}")
        runner = NormalizationQualityRunner(resources)
        runs = []
        for model_id in selected_ids:
            candidate = model_by_id[model_id]
            if candidate.provider != "ramalama":
                raise ValueError(
                    "normalization-quality Slice 1 supports ramalama models only; "
                    f"{model_id} uses {candidate.provider!r}"
                )
            if not candidate.model_ref:
                raise ValueError(f"model {model_id} has no model_ref")
            if active_server is not None:
                active_server.stop()
                active_server = None
            model_config = replace(
                base_config,
                model=candidate.model_ref,
                cache_directory=None if no_cache else base_config.cache_directory,
                server=replace(base_config.server, model=candidate.model_ref),
            )
            active_server = RamaLamaServerManager(model_config)
            if model_config.server.enabled:
                active_server.start()
            typer.echo(f"Normalization review    : {model_id}")
            run = runner.run(
                corpus,
                gateway=OpenAICompatibleLlmGateway(model_config),
                model_id=model_id,
                model_ref=candidate.model_ref,
                max_tokens=(max_tokens or candidate.generation.max_output_tokens or 384),
                limit=limit,
                progress=_progress(model_id),
            )
            runs.append(run)
            typer.echo(
                f"Model result             : reviewed={run.reviewed} "
                f"suspicious={run.suspicious} failed={run.failed} cached={run.cached}"
            )
        json_path, jsonl_path, markdown_path = NormalizationQualityReporter().write(
            tuple(runs), output
        )
    except (OSError, ValueError, RamaLamaServerError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    finally:
        if active_server is not None:
            try:
                active_server.stop()
            except RamaLamaServerError as exc:
                typer.echo(f"Warning: failed to stop LLM server: {exc}", err=True)
    typer.echo(f"Qualification JSON      : {json_path}")
    typer.echo(f"Findings JSONL          : {jsonl_path}")
    typer.echo(f"Qualification Markdown  : {markdown_path}")


def _default_model_ids(model_by_id: dict[str, object]) -> tuple[str, ...]:
    available = tuple(model_id for model_id in DEFAULT_MODELS if model_id in model_by_id)
    if available:
        return available
    raise ValueError("no default normalization-quality models are present; pass --model")


def _progress(model_id: str):
    def report(current: int, total: int, case) -> None:
        state = "failed" if case.error else case.status.value
        typer.echo(f"[{current:03d}/{total:03d}] {model_id}: {case.reference} -> {state}")

    return report
