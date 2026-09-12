"""Opt-in sparse cascade; existing qualification workflow remains unchanged."""

from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import typer
import yaml

from standards_atlas.adapters.llm import (
    CodexCliConfig,
    CodexCliLlmGateway,
    LlmConfig,
    OpenAICompatibleLlmGateway,
    RamaLamaServerManager,
)
from standards_atlas.application.semantic_qualification.mixed_applicability import (
    run_mixed_applicability,
)
from standards_atlas.application.semantic_qualification.mixed_evidence import MixedConsensusReport
from standards_atlas.application.semantic_qualification.partial_cascade import run_partial_cascade
from standards_atlas.application.semantic_qualification.partial_cascade_archive import (
    archive_partial_cascade,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    _run_lock,
    load_partial_inputs,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.cli import defaults
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.cli.runtime_managers import managed_mcp_server


@contextmanager
def partial_gateway_context(model, *, config: Path, mcp_config: Path):
    """Use the same lazy, bounded model lifecycle as partial-proposals."""
    with ExitStack() as stack:
        if model.provider == "codex":
            manager = managed_mcp_server(mcp_config)
            stack.enter_context(manager.ensure_running(autostart=True, autostop=True))
            yield CodexCliLlmGateway(CodexCliConfig())
        elif model.provider == "ramalama":
            base = LlmConfig.load(config)
            reference = model.model_ref or model.id
            configured = replace(
                base, model=reference, server=replace(base.server, model=reference)
            )
            manager = RamaLamaServerManager(configured)
            if configured.server.enabled and not manager.status().running:
                manager.start()
                stack.callback(manager.stop)
            yield OpenAICompatibleLlmGateway(configured)
        else:
            raise ValueError(f"unsupported partial cascade provider: {model.provider}")


@evaluation_app.command("partial-cascade")
def run_partial_cascade_command(
    manifest: Annotated[Path, typer.Option("--manifest", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    run: Annotated[Path | None, typer.Option("--run", exists=True)] = None,
    dataset: Annotated[Path | None, typer.Option("--dataset", exists=True, dir_okay=False)] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Infer open attributes and run the existing detail policy."),
    ] = False,
    archive_output: Annotated[
        Path | None, typer.Option("--archive-output", file_okay=False)
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Frozen first-N subset, not a pending-work limit."),
    ] = None,
    resources: Annotated[
        Path, typer.Option("--resources", file_okay=False)
    ] = defaults.DEFAULT_EVALUATION_RESOURCES,
    config: Annotated[Path, typer.Option("--config")] = defaults.DEFAULT_LLM_CONFIG,
    mcp_config: Annotated[Path, typer.Option("--mcp-config")] = defaults.DEFAULT_MCP_CONFIG,
) -> None:
    """Plan or execute source-backed partial stages; archive for explicit adoption.

    Default planning is model-free. The immutable completion profile is derived
    from the configured required decisions and cannot be reduced through this CLI.
    No canonical or public files are modified by this command.
    """
    try:
        matrix = QualificationMatrixManifest.load(manifest)
        source = load_partial_inputs(run=run, dataset=dataset)
        source_path = (run or dataset).resolve()
        if output.resolve() == source_path or (
            source_path.is_dir() and output.resolve().is_relative_to(source_path)
        ):
            raise ValueError("cascade output must be separate from input artifacts")
        if matrix.dataset_version != source.dataset_version or (
            source.corpus_id != "source-dataset" and matrix.corpus_id != source.corpus_id
        ):
            raise ValueError("manifest corpus/version differs from source selection")
        examples = source.examples[:limit] if limit is not None else source.examples

        def gateway(model):
            return partial_gateway_context(model, config=config, mcp_config=mcp_config)

        result = run_partial_cascade(
            manifest=matrix,
            examples=examples,
            resources=resources,
            output_directory=output,
            execute=execute,
            gateway_context=gateway,
            source_fingerprints=source.fingerprints,
            progress=typer.echo,
        )
        if execute:
            with _run_lock(output):
                mixed = MixedConsensusReport.model_validate_json(
                    (output / "mixed-consensus-report.json").read_bytes()
                )
                policy = run_mixed_applicability(
                    report=mixed,
                    examples=examples,
                    manifest=matrix,
                    root=output,
                    resources=resources,
                    gateway_context=gateway,
                )
                if policy is not None:
                    policy_path = output / "policy/applicability-policy-run.json"
                    typer.echo(f"Final applicability policy: {policy_path}")
        archived = (
            archive_partial_cascade(
                root=output,
                archive_directory=archive_output,
                resources=resources,
            )
            if archive_output is not None
            else None
        )
    except (
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
        BadZipFile,
        yaml.YAMLError,
    ) as exc:
        typer.echo(f"Partial cascade failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Clause accounting / required decisions: {result['metrics']}")
    calls = result["request_timing_current_invocation"]["request_count"]
    typer.echo(f"Fresh cascade gateway calls: {calls}")
    typer.echo(f"Report: {output / 'partial-cascade-report.json'}")
    if archived is not None:
        typer.echo(f"Verified archive: {archived}")
    typer.echo(
        "Opt-in operational cascade; not a fresh-repeat qualification or automatic publication."
    )
