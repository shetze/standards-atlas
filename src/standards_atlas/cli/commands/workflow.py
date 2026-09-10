"""Command-line interface for Standards Atlas workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.application.semantic_qualification.clause_access import SamplingStrategy
from standards_atlas.application.workflow import (
    EndToEndWorkflowService,
    QualificationWorkflowPlanner,
    WorkflowManifestLoader,
    WorkflowManifestType,
    WorkflowPlan,
    WorkflowRunReporter,
    WorkflowStage,
    WorkflowTask,
    parse_manifest_options,
)
from standards_atlas.application.workflow.enrichments_plan import EnrichmentsWorkflowPlanner
from standards_atlas.application.workflow.knowledge_plan import (
    knowledge_plan,
    with_knowledge_restore,
)
from standards_atlas.application.workspace import WorkspaceLayout
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import catalog_app, workflow_app
from standards_atlas.cli.composition import build_workflow_service
from standards_atlas.cli.workflow_runner import InProcessWorkflowCommandRunner


@catalog_app.command("validate")
def validate_catalog(
    manifest: Annotated[Path, typer.Argument(help="YAML standards manifest.")],
) -> None:
    model = YamlStandardCatalogReader().read(manifest)
    typer.echo(f"Manifest schema        : {model.schema_version}")
    typer.echo(f"Knowledge domains      : {len(model.knowledge_domains)}")
    typer.echo(f"Industry sectors       : {len(model.industry_sectors)}")
    typer.echo(f"Standard families      : {len(model.families)}")
    typer.echo(f"Profiles               : {len(model.profiles)}")
    typer.echo(f"Doorstop hierarchies   : {len(model.doorstop_hierarchies)}")


@workflow_app.command("plan")
def plan_workflow(
    manifests: Annotated[
        list[str],
        typer.Option(
            "--manifests",
            help="Workflow manifests; repeat or provide comma-separated paths.",
        ),
    ],
    task: Annotated[
        WorkflowTask, typer.Option("--task", help="Workflow task to plan.")
    ] = WorkflowTask.DOCUMENTS,
    family: Annotated[
        list[str] | None, typer.Option("--family", help="Family key; repeat as needed.")
    ] = cli_defaults.DEFAULT_NONE,
    profile: Annotated[
        str | None, typer.Option("--profile", help="Manifest profile key.")
    ] = cli_defaults.DEFAULT_NONE,
    all_families: Annotated[
        bool, typer.Option("--all", help="Plan all manifest families.")
    ] = cli_defaults.DEFAULT_FALSE,
    hierarchy: Annotated[
        str | None, typer.Option("--hierarchy", help="Doorstop hierarchy key.")
    ] = cli_defaults.DEFAULT_NONE,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Regenerate all reproducible artifacts for the documents task.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    regenerate_docling: Annotated[
        bool,
        typer.Option(
            "--regenerate-docling",
            help="Regenerate Docling and downstream artifacts for qualification/enrichments.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Regenerate derived artifacts; qualification also recomputes its matrix.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Run qualification LLM inference without proposal reuse or response cache.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    fresh_applicability_policy: Annotated[
        bool,
        typer.Option(
            "--fresh-applicability-policy",
            help=(
                "Refresh only the applicability decision policy while reusing the "
                "persisted Presence qualification."
            ),
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    keep: Annotated[
        list[WorkflowStage] | None,
        typer.Option(
            "--keep",
            help="Reuse a stage while overwriting later artifacts; repeat as needed.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
    corpus_count: Annotated[
        int | None,
        typer.Option(
            "--corpus-count", min=1, help="Corpus size; enrichments defaults to all eligible."
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Limit clauses across qualification stages."),
    ] = None,
    corpus_strategy: Annotated[
        SamplingStrategy, typer.Option("--corpus-strategy")
    ] = SamplingStrategy.REPRESENTATIVE_STRATIFIED,
    corpus_seed: Annotated[
        int, typer.Option("--corpus-seed")
    ] = cli_defaults.DEFAULT_EVALUATION_SEED,
    knowledge_domain: Annotated[
        str, typer.Option("--knowledge-domain")
    ] = cli_defaults.DEFAULT_KNOWLEDGE_DOMAIN,
    corpus_output: Annotated[
        Path, typer.Option("--corpus-output", file_okay=False)
    ] = cli_defaults.DEFAULT_EVALUATION_CORPUS_ROOT,
    qualification_output: Annotated[
        Path, typer.Option("--qualification-output", file_okay=False)
    ] = Path(".atlas/data/evaluation/qualification"),
    adopt_run: Annotated[
        Path | None, typer.Option("--adopt-run", exists=True, help="Archive to adopt.")
    ] = None,
    publish_enrichments: Annotated[
        bool, typer.Option("--publish-enrichments", help="Public export in the knowledge task.")
    ] = False,
    restore_enrichments: Annotated[
        bool, typer.Option("--restore-enrichments", help="Restore persisted attributes before use.")
    ] = False,
    strict_evidence: Annotated[
        bool, typer.Option("--strict-evidence", help="Require private evidence when restoring.")
    ] = False,
    resume_after_context: Annotated[
        bool,
        typer.Option(
            "--resume-after-context",
            help="Enrichments only: verify saved context baseline and skip context inference.",
        ),
    ] = False,
    fail_on_context_failure: Annotated[
        bool,
        typer.Option(
            "--fail-on-context-failure",
            help=(
                "Enrichments only: stop after a document with invalid routing; "
                "default reports and continues."
            ),
        ),
    ] = False,
) -> None:
    """Plan either document publication or the full qualification workflow."""
    plan = _build_task_plan(
        manifests=tuple(manifests),
        task=task,
        family=tuple(family or ()),
        profile=profile,
        all_families=all_families,
        hierarchy=hierarchy,
        force=force,
        regenerate_docling=regenerate_docling,
        overwrite=overwrite,
        fresh=fresh,
        fresh_applicability_policy=fresh_applicability_policy,
        keep=tuple(keep or ()),
        corpus_count=corpus_count,
        limit=limit,
        corpus_strategy=corpus_strategy,
        corpus_seed=corpus_seed,
        knowledge_domain=knowledge_domain,
        corpus_output=corpus_output,
        qualification_output=qualification_output,
        adopt_run=adopt_run,
        publish_enrichments=publish_enrichments,
        restore_enrichments=restore_enrichments,
        strict_evidence=strict_evidence,
        fail_on_context_failure=fail_on_context_failure,
        resume_after_context=resume_after_context,
    )
    for step in plan.steps:
        gate = " [manual review gate]" if step.manual_gate else ""
        typer.echo(f"{step.family:20} {step.stage.value:20} {' '.join(step.command)}{gate}")


@workflow_app.command("run")
def run_workflow(
    manifests: Annotated[
        list[str],
        typer.Option(
            "--manifests",
            help="Workflow manifests; repeat or provide comma-separated paths.",
        ),
    ],
    task: Annotated[
        WorkflowTask, typer.Option("--task", help="Workflow task to execute.")
    ] = WorkflowTask.DOCUMENTS,
    family: Annotated[
        list[str] | None, typer.Option("--family", help="Family key; repeat as needed.")
    ] = cli_defaults.DEFAULT_NONE,
    profile: Annotated[
        str | None, typer.Option("--profile", help="Manifest profile key.")
    ] = cli_defaults.DEFAULT_NONE,
    all_families: Annotated[
        bool, typer.Option("--all", help="Run all manifest families.")
    ] = cli_defaults.DEFAULT_FALSE,
    hierarchy: Annotated[
        str | None, typer.Option("--hierarchy", help="Doorstop hierarchy key.")
    ] = cli_defaults.DEFAULT_NONE,
    continue_after_review: Annotated[
        bool,
        typer.Option(
            "--continue-after-review",
            help="Continue only when reviewed alignments already exist.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Regenerate all reproducible artifacts for the documents task.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    regenerate_docling: Annotated[
        bool,
        typer.Option(
            "--regenerate-docling",
            help="Regenerate Docling and downstream artifacts for qualification/enrichments.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Regenerate derived artifacts; qualification also recomputes its matrix.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Run qualification LLM inference without proposal reuse or response cache.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    fresh_applicability_policy: Annotated[
        bool,
        typer.Option(
            "--fresh-applicability-policy",
            help=(
                "Refresh only the applicability decision policy while reusing the "
                "persisted Presence qualification."
            ),
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    keep: Annotated[
        list[WorkflowStage] | None,
        typer.Option(
            "--keep",
            help="Reuse a stage while overwriting later artifacts; repeat as needed.",
        ),
    ] = cli_defaults.DEFAULT_NONE,
    corpus_count: Annotated[
        int | None,
        typer.Option(
            "--corpus-count", min=1, help="Corpus size; enrichments defaults to all eligible."
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Limit clauses across qualification stages."),
    ] = None,
    corpus_strategy: Annotated[
        SamplingStrategy, typer.Option("--corpus-strategy")
    ] = SamplingStrategy.REPRESENTATIVE_STRATIFIED,
    corpus_seed: Annotated[
        int, typer.Option("--corpus-seed")
    ] = cli_defaults.DEFAULT_EVALUATION_SEED,
    knowledge_domain: Annotated[
        str, typer.Option("--knowledge-domain")
    ] = cli_defaults.DEFAULT_KNOWLEDGE_DOMAIN,
    corpus_output: Annotated[
        Path, typer.Option("--corpus-output", file_okay=False)
    ] = cli_defaults.DEFAULT_EVALUATION_CORPUS_ROOT,
    qualification_output: Annotated[
        Path, typer.Option("--qualification-output", file_okay=False)
    ] = Path(".atlas/data/evaluation/qualification"),
    adopt_run: Annotated[
        Path | None, typer.Option("--adopt-run", exists=True, help="Archive to adopt.")
    ] = None,
    publish_enrichments: Annotated[
        bool, typer.Option("--publish-enrichments", help="Public export in the knowledge task.")
    ] = False,
    restore_enrichments: Annotated[
        bool, typer.Option("--restore-enrichments", help="Restore persisted attributes before use.")
    ] = False,
    strict_evidence: Annotated[
        bool, typer.Option("--strict-evidence", help="Require private evidence when restoring.")
    ] = False,
    resume_after_context: Annotated[
        bool,
        typer.Option(
            "--resume-after-context",
            help="Enrichments only: verify saved context baseline and skip context inference.",
        ),
    ] = False,
    fail_on_context_failure: Annotated[
        bool,
        typer.Option(
            "--fail-on-context-failure",
            help=(
                "Enrichments only: stop after a document with invalid routing; "
                "default reports and continues."
            ),
        ),
    ] = False,
) -> None:
    """Execute either document publication or the full qualification workflow."""
    plan = _build_task_plan(
        manifests=tuple(manifests),
        task=task,
        family=tuple(family or ()),
        profile=profile,
        all_families=all_families,
        hierarchy=hierarchy,
        force=force,
        regenerate_docling=regenerate_docling,
        overwrite=overwrite,
        fresh=fresh,
        fresh_applicability_policy=fresh_applicability_policy,
        keep=tuple(keep or ()),
        corpus_count=corpus_count,
        limit=limit,
        corpus_strategy=corpus_strategy,
        corpus_seed=corpus_seed,
        knowledge_domain=knowledge_domain,
        corpus_output=corpus_output,
        qualification_output=qualification_output,
        adopt_run=adopt_run,
        publish_enrichments=publish_enrichments,
        restore_enrichments=restore_enrichments,
        strict_evidence=strict_evidence,
        fail_on_context_failure=fail_on_context_failure,
        resume_after_context=resume_after_context,
    )
    # Keep cross-invocation workflow checkpoints so an interrupted workflow can
    # resume from the first incomplete step. Other scratch state is disposable.
    WorkspaceLayout(Path.cwd()).clear_work(preserve_workflow=True)
    service = build_workflow_service(Path.cwd())
    result = service.execute(
        plan,
        project_root=Path.cwd(),
        continue_after_review=continue_after_review,
        **(
            {"runner": InProcessWorkflowCommandRunner()} if task is WorkflowTask.ENRICHMENTS else {}
        ),
    )
    if result.completed:
        report_json, report_md = WorkflowRunReporter().write(
            plan,
            result,
            project_root=Path.cwd(),
            manifest_paths=_resolved_manifest_paths(tuple(manifests)),
            hierarchy_key=hierarchy,
            task=task,
        )
        typer.echo(f"Workflow completed      : {len(result.executed_steps)} steps")
        typer.echo(f"Run report JSON         : {report_json}")
        typer.echo(f"Run report Markdown     : {report_md}")
        return

    typer.echo(f"Workflow paused         : {len(result.executed_steps)} steps executed")
    if result.blocked_documents:
        typer.echo("Review required for     : " + ", ".join(result.blocked_documents))
    if result.blocked_families:
        typer.echo("AtlasData review for    : " + ", ".join(result.blocked_families))
    typer.echo("Continue after completing the reviews with --continue-after-review.")


def _build_task_plan(
    *,
    manifests: tuple[str, ...],
    task: WorkflowTask,
    family: tuple[str, ...],
    profile: str | None,
    all_families: bool,
    hierarchy: str | None,
    force: bool,
    regenerate_docling: bool,
    overwrite: bool,
    fresh: bool,
    fresh_applicability_policy: bool,
    keep: tuple[WorkflowStage, ...],
    corpus_count: int | None,
    limit: int | None,
    corpus_strategy: SamplingStrategy,
    corpus_seed: int,
    knowledge_domain: str,
    corpus_output: Path,
    qualification_output: Path,
    adopt_run: Path | None = None,
    publish_enrichments: bool = False,
    restore_enrichments: bool = False,
    strict_evidence: bool = False,
    fail_on_context_failure: bool = False,
    resume_after_context: bool = False,
) -> WorkflowPlan:
    if resume_after_context and task is not WorkflowTask.ENRICHMENTS:
        raise typer.BadParameter("--resume-after-context is only available for --task enrichments")

    if fail_on_context_failure and task is not WorkflowTask.ENRICHMENTS:
        raise typer.BadParameter("--fail-on-context-failure requires --task enrichments")
    if (adopt_run is not None or publish_enrichments) and task is not WorkflowTask.KNOWLEDGE:
        raise typer.BadParameter("--adopt-run/--publish-enrichments require --task knowledge")
    if strict_evidence and not (
        restore_enrichments or publish_enrichments or task is WorkflowTask.ENRICHMENTS
    ):
        raise typer.BadParameter("--strict-evidence requires restore or publication")
    if task is WorkflowTask.KNOWLEDGE and (
        force
        or overwrite
        or fresh
        or fresh_applicability_policy
        or regenerate_docling
        or keep
        or limit is not None
    ):
        raise typer.BadParameter("knowledge task does not accept qualification/force options")
    if adopt_run is not None and adopt_run.resolve().is_relative_to(Path(".atlas/work").resolve()):
        raise typer.BadParameter("--adopt-run must be outside disposable .atlas/work")
    if force and overwrite:
        raise typer.BadParameter("--force and --overwrite are mutually exclusive")
    if keep and not overwrite:
        raise typer.BadParameter("--keep requires --overwrite")
    if task is WorkflowTask.DOCUMENTS and regenerate_docling:
        raise typer.BadParameter("--regenerate-docling is only valid for --task qualification")
    if task is WorkflowTask.DOCUMENTS and limit is not None:
        raise typer.BadParameter("--limit is only valid for --task qualification")
    if task is WorkflowTask.DOCUMENTS and fresh:
        raise typer.BadParameter("--fresh is only valid for --task qualification")
    if task is WorkflowTask.DOCUMENTS and fresh_applicability_policy:
        raise typer.BadParameter(
            "--fresh-applicability-policy is only valid for --task qualification"
        )
    if fresh and fresh_applicability_policy:
        raise typer.BadParameter("--fresh and --fresh-applicability-policy are mutually exclusive")
    if task in {WorkflowTask.QUALIFICATION, WorkflowTask.ENRICHMENTS} and force:
        raise typer.BadParameter(
            "--force is only valid for --task documents; use --regenerate-docling or --overwrite"
        )

    try:
        resolved = WorkflowManifestLoader().load(parse_manifest_options(manifests))
        standards_manifest = resolved.require(WorkflowManifestType.STANDARDS)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    qualification_manifest = resolved.optional(WorkflowManifestType.QUALIFICATION_MATRIX)
    if (
        task in {WorkflowTask.QUALIFICATION, WorkflowTask.ENRICHMENTS}
        and qualification_manifest is None
    ):
        raise typer.BadParameter(
            f"--task {task.value} requires a manifest of type 'qualification_matrix'"
        )
    if hierarchy is not None and (family or profile is not None or all_families):
        raise typer.BadParameter("select exactly one family/profile/all/hierarchy mode")
    model = YamlStandardCatalogReader().read(standards_manifest)
    keys = (
        model.doorstop_hierarchy(hierarchy).families
        if hierarchy is not None
        else _select_manifest_families(model, family, profile, all_families)
    )
    if task is WorkflowTask.ENRICHMENTS:
        assert qualification_manifest is not None
        try:
            return EnrichmentsWorkflowPlanner().plan(
                model,
                family_keys=keys,
                catalog_root=Path.cwd(),
                standards_manifest=standards_manifest,
                qualification_manifest=qualification_manifest,
                corpus_count=corpus_count,
                limit=limit,
                corpus_strategy=corpus_strategy,
                corpus_seed=corpus_seed,
                knowledge_domain=knowledge_domain,
                hierarchy_key=hierarchy,
                regenerate_docling=regenerate_docling,
                overwrite=overwrite,
                fresh=fresh,
                fresh_applicability_policy=fresh_applicability_policy,
                keep_stages=keep,
                corpus_output=corpus_output,
                qualification_output=qualification_output,
                restore_enrichments=restore_enrichments,
                strict_evidence=strict_evidence,
                fail_on_context_failure=fail_on_context_failure,
                resume_after_context=resume_after_context,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    if task is WorkflowTask.KNOWLEDGE:
        try:
            return knowledge_plan(
                model,
                family_keys=keys,
                catalog_root=Path.cwd(),
                manifest=standards_manifest,
                adopt_run=adopt_run,
                restore=restore_enrichments,
                publish=publish_enrichments,
                strict_evidence=strict_evidence,
                knowledge_domain=knowledge_domain,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    if task is WorkflowTask.DOCUMENTS:
        plan = EndToEndWorkflowService().plan(
            model,
            family_keys=keys,
            catalog_root=Path.cwd(),
            force=force or overwrite,
            keep_stages=keep,
            hierarchy_key=hierarchy,
        )
        return (
            with_knowledge_restore(
                plan,
                manifest=standards_manifest,
                strict_evidence=strict_evidence,
                knowledge_domain=knowledge_domain,
            )
            if restore_enrichments
            else plan
        )

    assert qualification_manifest is not None
    qualification = QualificationWorkflowPlanner().plan(
        model,
        family_keys=keys,
        catalog_root=Path.cwd(),
        manifest_path=qualification_manifest,
        corpus_count=500 if corpus_count is None else corpus_count,
        limit=limit,
        corpus_strategy=corpus_strategy,
        corpus_seed=corpus_seed,
        knowledge_domain=knowledge_domain,
        hierarchy_key=hierarchy,
        regenerate_docling=regenerate_docling,
        overwrite=overwrite or regenerate_docling,
        fresh=fresh,
        fresh_applicability_policy=fresh_applicability_policy,
        keep_stages=keep,
        corpus_output=corpus_output,
        qualification_output=qualification_output,
    )
    plan = WorkflowPlan(
        families=qualification.document_plan.families,
        steps=qualification.steps,
        force=qualification.document_plan.force,
        kept_stages=qualification.document_plan.kept_stages,
        fresh_repetition_stages=qualification.fresh_repetition_stages,
    )
    return (
        with_knowledge_restore(
            plan,
            manifest=standards_manifest,
            strict_evidence=strict_evidence,
            knowledge_domain=knowledge_domain,
        )
        if restore_enrichments
        else plan
    )


def _resolved_manifest_paths(values: tuple[str, ...]) -> tuple[Path, ...]:
    try:
        return WorkflowManifestLoader().load(parse_manifest_options(values)).paths
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _select_manifest_families(
    model,
    families: tuple[str, ...],
    profile: str | None,
    all_families: bool,
) -> tuple[str, ...]:
    selected = sum((bool(families), profile is not None, all_families))
    if selected != 1:
        raise typer.BadParameter("select exactly one of --family, --profile, or --all")
    if families:
        for key in families:
            model.family(key)
        return families
    if profile is not None:
        return model.profile(profile).families
    return tuple(family.key for family in model.families)


@workflow_app.command("archive-baseline")
def archive_baseline(
    document: Annotated[list[str], typer.Option("--document", help="Selected physical documents.")],
    manifest: Annotated[list[Path], typer.Option("--manifest", help="Standards manifest first.")],
    selection: Annotated[str, typer.Option("--selection", help="Workflow selection identity.")],
    phase: Annotated[str, typer.Option("--phase", help="context or published")],
    reports_root: Annotated[Path, typer.Option("--reports-root")],
    output: Annotated[Path, typer.Option("--output", help="Private baseline receipt.")],
    workspace: Annotated[Path, typer.Option("--workspace", "-w")] = cli_defaults.DEFAULT_WORKSPACE,
    corpus_count: Annotated[int | None, typer.Option("--corpus-count", min=1)] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    strict_context: Annotated[bool, typer.Option("--strict-context")] = False,
    verify_existing: Annotated[bool, typer.Option("--verify-existing")] = False,
) -> None:
    """Freeze a private baseline; context quality failures are recorded, not suppressed."""
    from standards_atlas.adapters.workflow.baseline_archive import archive_enrichment_baseline

    try:
        if verify_existing:
            from standards_atlas.adapters.workflow.baseline_resume import verify_context_baseline

            if phase != "context":
                raise ValueError("only the context baseline can be resumed")
            result = verify_context_baseline(
                project_root=Path.cwd(),
                workspace=workspace,
                document_keys=tuple(document),
                manifest_paths=tuple(manifest),
                selection=selection,
                receipt=output,
                corpus_count=corpus_count,
                limit=limit,
                strict_context=strict_context,
            )
            typer.echo(f"Context baseline reused: {result['archive']}")
            typer.echo("Context inference skipped; failed clauses remain recorded in the baseline.")
            return
        result = archive_enrichment_baseline(
            project_root=Path.cwd(),
            workspace=workspace,
            document_keys=tuple(document),
            manifest_paths=tuple(manifest),
            selection=selection,
            phase=phase,
            reports_root=reports_root,
            output=output,
            corpus_count=corpus_count,
            limit=limit,
            strict_context=strict_context,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"Cannot archive enrichment baseline: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    summary = result["summary"]
    typer.echo(f"Baseline phase        : {phase}")
    typer.echo(f"Baseline status       : {result['status']} (not semantically verified)")
    typer.echo(f"Context documents     : {summary['documents']}")
    typer.echo(f"Context failures      : {summary['failed']}")
    typer.echo(f"Older values retained : {summary['failed_with_retained_value']}")
    typer.echo(f"Unresolved scopes     : {summary['unresolved_scope_targets']}")
    typer.echo(f"Unresolved references : {summary['unresolved_reference_targets']}")
    typer.echo(f"Baseline archive      : {result['archive']}")
    typer.echo(f"Baseline receipt      : {output}")
