"""CLI commands for applicability policy replay, evaluation, and selective inference."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Protocol

import typer

from standards_atlas.adapters.llm import (
    LlmConfig,
    OpenAICompatibleLlmGateway,
    RamaLamaServerManager,
)
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    LlmHealth,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.applicability_decision_policy import (
    POLICY_MODEL_ID,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    APPLICABILITY_DETAIL_ARTIFACT_DIRECTORY,
    APPLICABILITY_DETAIL_FAILURES_FILENAME,
    APPLICABILITY_DETAIL_REPORT_FILENAME,
    APPLICABILITY_DETAIL_SELECTION_FILENAME,
    ApplicabilityDetailEnrichmentConfig,
    ApplicabilityDetailEnrichmentReport,
    ApplicabilityDetailEnrichmentService,
    ApplicabilityDetailSelection,
    build_applicability_detail_selection,
    load_applicability_detail_report,
    load_applicability_detail_selection,
    persist_applicability_detail_report,
    persist_applicability_detail_selection,
    validate_reused_applicability_detail_selection,
)
from standards_atlas.application.semantic_qualification.applicability_policy_evaluation import (
    evaluate_applicability_policy,
)
from standards_atlas.application.semantic_qualification.applicability_policy_replay import (
    ApplicabilityPolicyReplayReport,
    replay_applicability_policy,
)
from standards_atlas.application.semantic_qualification.applicability_policy_qualification import (
    APPLICABILITY_POLICY_EVALUATION_FILENAME,
    APPLICABILITY_POLICY_RUN_FILENAME,
    APPLICABILITY_POLICY_SELECTION_FILENAME,
    APPLICABILITY_POLICY_STATE_FILENAME,
    ApplicabilityPolicyQualificationMode,
    ApplicabilityPolicyRunState,
)
from standards_atlas.application.semantic_qualification.applicability_policy_runner import (
    CONFIRMATION_PROMPT_VERSION,
    CONFIRMATION_TASK_VERSION,
    PRIMARY_PROMPT_VERSION,
    PRIMARY_TASK_VERSION,
    RESCUE_PROMPT_VERSION,
    RESCUE_TASK_VERSION,
    ApplicabilityPolicyRole,
    ApplicabilityPolicyRunReport,
    applicability_policy_inference_required,
    run_applicability_policy,
)
from standards_atlas.application.semantic_qualification.consensus import ConsensusReport
from standards_atlas.application.semantic_qualification.proposals import SemanticTaskRepository
from standards_atlas.application.semantic_qualification.qualification_coverage import (
    QUALIFICATION_COVERAGE_FILENAME,
    load_qualification_coverage,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QUALIFICATION_SELECTION_FILENAME,
    ensure_qualification_run_snapshots,
    examples_for_persisted_selection,
    load_qualification_run_selection,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.domain.model import ApplicabilityFunction, OtherApplicabilityTarget


@evaluation_app.command("applicability-policy-replay")
def replay_applicability_policy_command(
    run_archive: Annotated[Path, typer.Option("--run", exists=True, dir_okay=False)],
    primary: Annotated[Path, typer.Option("--primary", exists=True, dir_okay=False)],
    rescue: Annotated[Path, typer.Option("--rescue", exists=True, dir_okay=False)],
    confirmation: Annotated[
        Path,
        typer.Option("--confirmation", exists=True, dir_okay=False),
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Replay D4 OR (D3 AND D1) from persisted artifacts without inference."""
    try:
        report = replay_applicability_policy(
            run_archive=run_archive,
            primary_report_path=primary,
            rescue_report_path=rescue,
            confirmation_report_path=confirmation,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Policy                   : {report.policy_id} {report.policy_version}")
    typer.echo(f"Consensus clauses        : {report.consensus_clause_count}")
    typer.echo(f"Detail selection         : {report.selected_clause_count}")
    typer.echo(f"Final positive           : {report.final_positive_count}")
    typer.echo(f"Final negative           : {report.final_negative_count}")
    typer.echo(f"Final unknown            : {report.final_unknown_count}")
    typer.echo(f"Report                   : {output}")


@evaluation_app.command("applicability-policy-evaluate")
def evaluate_applicability_policy_command(
    golden: Annotated[Path, typer.Option("--golden", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
    replay: Annotated[
        Path | None,
        typer.Option("--replay", exists=True, dir_okay=False),
    ] = None,
    run_report: Annotated[
        Path | None,
        typer.Option("--run-report", exists=True, dir_okay=False),
    ] = None,
    max_false_positive: Annotated[int, typer.Option("--max-fp", min=0)] = 2,
    max_false_negative: Annotated[int, typer.Option("--max-fn", min=0)] = 2,
) -> None:
    """Evaluate one persisted policy replay or selective run against published gold."""
    try:
        if (replay is None) == (run_report is None):
            raise ValueError("select exactly one of --replay or --run-report")
        corpus = ApplicabilityGoldenCorpus.load(golden)
        if replay is not None:
            policy_report = ApplicabilityPolicyReplayReport.load(replay)
        else:
            assert run_report is not None
            policy_report = ApplicabilityPolicyRunReport.model_validate_json(
                run_report.read_text(encoding="utf-8")
            )
        report = evaluate_applicability_policy(
            corpus,
            policy_report,
            max_false_positive=max_false_positive,
            max_false_negative=max_false_negative,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    metrics = report.metrics
    typer.echo(f"Published gold cases     : {report.published_cases}")
    typer.echo(f"Matched gold cases       : {report.matched_cases}")
    typer.echo(f"Missing gold cases       : {len(report.missing_cases)}")
    typer.echo(f"Unknown gold decisions   : {len(report.unknown_cases)}")
    typer.echo(f"False positives          : {metrics.false_positive} / {report.max_false_positive}")
    typer.echo(f"False negatives          : {metrics.false_negative} / {report.max_false_negative}")
    typer.echo(f"Qualification passed     : {'yes' if report.passed else 'no'}")
    typer.echo(f"Report                   : {output}")


class _RunningStatus(Protocol):
    running: bool


class _PolicyServer(Protocol):
    def status(self) -> _RunningStatus: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


@contextmanager
def _managed_policy_server(server: _PolicyServer, *, enabled: bool) -> Iterator[None]:
    started_for_run = False
    try:
        if enabled and not server.status().running:
            server.start()
            started_for_run = True
        yield
    finally:
        if started_for_run:
            server.stop()


class _CountingGateway(LlmGateway):
    """Count low-level provider attempts, including retries."""

    def __init__(self, delegate: LlmGateway) -> None:
        self._delegate = delegate
        self.request_count = 0

    def health(self) -> LlmHealth:
        return self._delegate.health()

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        self.request_count += 1
        return self._delegate.generate_structured(request)


@evaluation_app.command("applicability-policy-run")
def run_applicability_policy_command(
    manifest_path: Annotated[Path, typer.Option("--manifest", exists=True, readable=True)],
    run_directory: Annotated[
        Path,
        typer.Option(
            "--run",
            file_okay=False,
            help="Qualification run directory containing the persisted run selection.",
        ),
    ],
    consensus_path: Annotated[
        Path | None,
        typer.Option(
            "--consensus",
            exists=True,
            readable=True,
            dir_okay=False,
            help="Override the final consensus-report.json selected by the manifest.",
        ),
    ] = None,
    resources: Annotated[Path, typer.Option("--resources", file_okay=False)] = (
        cli_defaults.DEFAULT_EVALUATION_RESOURCES
    ),
    config_path: Annotated[Path, typer.Option("--config", exists=True, readable=True)] = (
        cli_defaults.DEFAULT_LLM_CONFIG
    ),
    corpus_root: Annotated[Path, typer.Option("--corpus-root", file_okay=False)] = (
        cli_defaults.DEFAULT_EVALUATION_CORPUS_ROOT
    ),
    output_directory: Annotated[
        Path | None,
        typer.Option(
            "--output-directory",
            file_okay=False,
            help="Policy artifact directory; defaults to <run>/applicability-policy.",
        ),
    ] = None,
    qualification_mode: Annotated[
        ApplicabilityPolicyQualificationMode | None,
        typer.Option(
            "--qualification-mode",
            help="Qualification freshness scope recorded for this policy run.",
        ),
    ] = None,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Start a new policy repetition and keep the LLM cache disabled on resume.",
        ),
    ] = False,
) -> None:
    """Run Mistral v4 -> v3 -> v1 only where each policy stage can affect the result."""

    manifest = QualificationMatrixManifest.load(manifest_path)
    base_detail_config = manifest.applicability_detail_enrichment
    if not base_detail_config.enabled:
        raise typer.BadParameter("applicability detail enrichment is disabled in the manifest")
    policy_config = manifest.applicability_decision_policy
    configured_model_id = policy_config.model if policy_config.enabled else POLICY_MODEL_ID
    model = next((item for item in manifest.models if item.id == configured_model_id), None)
    if model is None:
        raise typer.BadParameter(
            "qualified applicability policy model "
            f"{POLICY_MODEL_ID!r} is absent from manifest.models"
        )
    if model.provider != "ramalama" or not model.model_ref:
        raise typer.BadParameter(
            "qualified applicability policy currently requires a ramalama model with model_ref"
        )

    selection_path = run_directory / QUALIFICATION_SELECTION_FILENAME
    if not selection_path.is_file():
        raise typer.BadParameter(f"qualification clause selection not found: {selection_path}")
    run_selection = load_qualification_run_selection(selection_path)
    ensure_qualification_run_snapshots(
        selection_root=run_directory,
        selection=run_selection,
        corpus_root=corpus_root,
    )
    if (
        run_selection.task != manifest.task
        or run_selection.dataset_version != manifest.dataset_version
        or run_selection.corpus_id != manifest.corpus_id
    ):
        raise typer.BadParameter(
            "persisted qualification selection does not match the qualification manifest"
        )
    examples = examples_for_persisted_selection(
        selection_root=run_directory,
        selection=run_selection,
    )

    resolved_consensus_path = consensus_path or (
        manifest.consensus.output_directory / manifest.matrix_id / "consensus-report.json"
    )
    if not resolved_consensus_path.is_file():
        raise typer.BadParameter(
            f"final qualification consensus not found: {resolved_consensus_path}"
        )
    consensus = ConsensusReport.model_validate_json(
        resolved_consensus_path.read_text(encoding="utf-8")
    )
    expected_prompt_selection = manifest.consensus.prompt_selection.model_dump()
    if (
        consensus.matrix_id != manifest.matrix_id
        or consensus.corpus_id != manifest.corpus_id
        or consensus.prompt_id != manifest.consensus.prompt_id
        or consensus.reasoning_mode_id != manifest.consensus.reasoning_mode_id
        or consensus.prompt_selection != expected_prompt_selection
    ):
        raise typer.BadParameter(
            "final qualification consensus does not match the qualification manifest"
        )

    coverage_path = run_directory / QUALIFICATION_COVERAGE_FILENAME
    if not coverage_path.is_file():
        raise typer.BadParameter(f"qualification coverage not found: {coverage_path}")
    coverage = load_qualification_coverage(coverage_path)

    resolved_output = output_directory or (run_directory / "applicability-policy")
    if fresh:
        _clear_policy_artifacts(resolved_output)
    resolved_output.mkdir(parents=True, exist_ok=True)
    policy_selection_path = resolved_output / APPLICABILITY_POLICY_SELECTION_FILENAME
    try:
        detail_selection = _resolve_policy_selection(
            selection_path=policy_selection_path,
            fresh=fresh,
            run_selection=run_selection,
            examples=examples,
            consensus=consensus,
            coverage=coverage,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    persist_applicability_detail_selection(detail_selection, policy_selection_path)

    state_path = resolved_output / APPLICABILITY_POLICY_STATE_FILENAME
    if state_path.is_file() and not fresh:
        state = ApplicabilityPolicyRunState.model_validate_json(
            state_path.read_text(encoding="utf-8")
        )
        if (
            state.source_selection_sha256 != detail_selection.fingerprint
            or state.model_id != model.id
            or state.model_ref != model.model_ref
        ):
            raise typer.BadParameter(
                "existing applicability policy run state belongs to a different "
                "selection or model; use --fresh to replace it"
            )
        if qualification_mode is not None and qualification_mode != state.qualification_mode:
            raise typer.BadParameter(
                "existing applicability policy run state uses a different "
                "qualification mode; use --fresh to replace it"
            )
    else:
        resolved_mode = qualification_mode or ApplicabilityPolicyQualificationMode.OPERATIONAL
        state = ApplicabilityPolicyRunState(
            source_selection_sha256=detail_selection.fingerprint,
            model_id=model.id,
            model_ref=model.model_ref,
            cache_disabled=fresh,
            fresh_requested=fresh,
            qualification_mode=resolved_mode,
        )
        state_path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")

    llm_config = LlmConfig.load(config_path)
    llm_config = replace(
        llm_config,
        model=model.model_ref,
        timeout_seconds=base_detail_config.timeout_seconds,
        cache_directory=None if state.cache_disabled else llm_config.cache_directory,
        server=replace(llm_config.server, model=model.model_ref),
    )
    gateway = _CountingGateway(OpenAICompatibleLlmGateway(llm_config))

    role_specs = {
        "primary": (PRIMARY_TASK_VERSION, PRIMARY_PROMPT_VERSION),
        "rescue": (RESCUE_TASK_VERSION, RESCUE_PROMPT_VERSION),
        "confirmation": (CONFIRMATION_TASK_VERSION, CONFIRMATION_PROMPT_VERSION),
    }
    services: dict[ApplicabilityPolicyRole, ApplicabilityDetailEnrichmentService] = {}
    existing: dict[ApplicabilityPolicyRole, ApplicabilityDetailEnrichmentReport | None] = {}
    for role, (task_version, prompt_version) in role_specs.items():
        role_dir = resolved_output / role
        role_dir.mkdir(parents=True, exist_ok=True)
        task, schema = SemanticTaskRepository(resources / "tasks").load(
            base_detail_config.task,
            task_version,
        )
        prompt = PromptRepository(resources / "prompts").load(
            base_detail_config.task,
            prompt_version,
        )
        _validate_policy_task_taxonomy(task)
        role_config = ApplicabilityDetailEnrichmentConfig.model_validate(
            {
                **base_detail_config.model_dump(),
                "task_version": task_version,
                "prompt_version": prompt_version,
                "model": model.id,
            }
        )
        services[role] = ApplicabilityDetailEnrichmentService(
            gateway,
            config=role_config,
            prompt=prompt,
            canonical_schema=schema,
            model_id=model.id,
            model_ref=model.model_ref,
            artifact_root=role_dir / APPLICABILITY_DETAIL_ARTIFACT_DIRECTORY,
        )
        report_path = role_dir / APPLICABILITY_DETAIL_REPORT_FILENAME
        existing[role] = (
            load_applicability_detail_report(report_path) if report_path.is_file() else None
        )

    last_processed = {role: 0 for role in role_specs}

    def checkpoint(
        role: ApplicabilityPolicyRole,
        role_selection: ApplicabilityDetailSelection,
        report: ApplicabilityDetailEnrichmentReport,
    ) -> None:
        role_dir = resolved_output / role
        persist_applicability_detail_selection(
            role_selection,
            role_dir / APPLICABILITY_DETAIL_SELECTION_FILENAME,
        )
        persist_applicability_detail_report(
            report,
            role_dir / APPLICABILITY_DETAIL_REPORT_FILENAME,
            role_dir / APPLICABILITY_DETAIL_FAILURES_FILENAME,
        )
        if report.processed_clause_count > last_processed[role]:
            latest = report.clauses[-1]
            typer.echo(
                f"Applicability policy {role:12}: "
                f"{report.processed_clause_count}/{report.selected_clause_count} "
                f"{latest.document_key}/{latest.clause_id} {latest.outcome.value}"
            )
            last_processed[role] = report.processed_clause_count

    try:
        inference_required = applicability_policy_inference_required(
            selection=detail_selection,
            primary_service=services["primary"],
            rescue_service=services["rescue"],
            confirmation_service=services["confirmation"],
            existing_primary=existing["primary"],
            existing_rescue=existing["rescue"],
            existing_confirmation=existing["confirmation"],
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    server = RamaLamaServerManager(llm_config)
    try:
        with _managed_policy_server(
            server,
            enabled=llm_config.server.enabled and inference_required,
        ):
            result = run_applicability_policy(
                selection=detail_selection,
                consensus=consensus,
                examples=examples,
                primary_service=services["primary"],
                rescue_service=services["rescue"],
                confirmation_service=services["confirmation"],
                existing_primary=existing["primary"],
                existing_rescue=existing["rescue"],
                existing_confirmation=existing["confirmation"],
                checkpoint=checkpoint,
                request_count=lambda: gateway.request_count,
                qualification_mode=state.qualification_mode,
                fresh_requested=state.fresh_requested,
            )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    for role in role_specs:
        checkpoint(role, result.selections[role], result.reports[role])
    run_report_path = resolved_output / APPLICABILITY_POLICY_RUN_FILENAME
    run_report_path.write_text(
        result.report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    evaluation_report = None
    if policy_config.enabled and policy_config.golden_corpus is not None:
        if not policy_config.golden_corpus.is_file():
            raise typer.BadParameter(
                f"applicability policy golden corpus not found: {policy_config.golden_corpus}"
            )
        golden = ApplicabilityGoldenCorpus.load(policy_config.golden_corpus)
        evaluation_report = evaluate_applicability_policy(
            golden,
            result.report,
            max_false_positive=policy_config.max_false_positive,
            max_false_negative=policy_config.max_false_negative,
        )
        evaluation_path = resolved_output / APPLICABILITY_POLICY_EVALUATION_FILENAME
        evaluation_path.write_text(
            evaluation_report.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

    typer.echo(
        f"Policy                   : {result.report.policy_id} {result.report.policy_version}"
    )
    typer.echo(f"Detail model             : {model.id} / {model.model_ref}")
    typer.echo(f"Presence selection       : {result.report.selected_clause_count}")
    for stage in result.report.stages:
        requests = (
            "n/a" if stage.provider_request_count is None else str(stage.provider_request_count)
        )
        typer.echo(
            f"{stage.role.title():24}: selected={stage.selected_clause_count} "
            f"pending={stage.pending_clause_count} provider_requests={requests}"
        )
    typer.echo(f"Final positive           : {result.report.final_positive_count}")
    typer.echo(f"Final negative           : {result.report.final_negative_count}")
    typer.echo(f"Final unknown            : {result.report.final_unknown_count}")
    typer.echo(f"Qualification mode       : {state.qualification_mode.value}")
    typer.echo(f"Cache disabled           : {'yes' if state.cache_disabled else 'no'}")
    if evaluation_report is not None:
        typer.echo(
            "Policy quality            : "
            f"{'passed' if evaluation_report.passed else 'failed'} "
            f"(FP={evaluation_report.metrics.false_positive}/"
            f"{evaluation_report.max_false_positive}, "
            f"FN={evaluation_report.metrics.false_negative}/"
            f"{evaluation_report.max_false_negative})"
        )
    typer.echo(f"Policy output directory  : {resolved_output}")
    typer.echo(f"Policy report            : {run_report_path}")



def _resolve_policy_selection(
    *,
    selection_path: Path,
    fresh: bool,
    run_selection: object,
    examples: tuple[object, ...],
    consensus: ConsensusReport,
    coverage: object,
) -> ApplicabilityDetailSelection:
    """Resolve the policy-owned selection against the current Presence result."""
    if selection_path.is_file() and not fresh:
        return validate_reused_applicability_detail_selection(
            persisted_selection=load_applicability_detail_selection(selection_path),
            run_selection=run_selection,
            examples=examples,
            consensus=consensus,
            coverage=coverage,
        )
    return build_applicability_detail_selection(
        run_selection=run_selection,
        examples=examples,
        consensus=consensus,
        coverage=coverage,
        task_version=PRIMARY_TASK_VERSION,
    )

def _validate_policy_task_taxonomy(task: object) -> None:
    expected_functions = tuple(item.value for item in ApplicabilityFunction)
    if getattr(task, "applicability_taxonomy", ()) != expected_functions:
        raise typer.BadParameter("applicability policy task ontology differs from domain taxonomy")
    expected_other_targets = tuple(item.value for item in OtherApplicabilityTarget)
    task_other_targets = getattr(task, "other_applicability_target_taxonomy", ())
    if task_other_targets and task_other_targets != expected_other_targets:
        raise typer.BadParameter(
            "applicability policy other-target ontology differs from domain taxonomy"
        )


def _clear_policy_artifacts(root: Path) -> None:
    for role in ("primary", "rescue", "confirmation"):
        shutil.rmtree(root / role, ignore_errors=True)
    for filename in (
        APPLICABILITY_POLICY_RUN_FILENAME,
        APPLICABILITY_POLICY_SELECTION_FILENAME,
        APPLICABILITY_POLICY_STATE_FILENAME,
        APPLICABILITY_POLICY_EVALUATION_FILENAME,
    ):
        (root / filename).unlink(missing_ok=True)
