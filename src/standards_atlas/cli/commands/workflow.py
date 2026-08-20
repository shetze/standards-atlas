"""Command-line interface for Standards Atlas workflows."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.application.semantic_qualification.clause_access import SamplingStrategy
from standards_atlas.application.semantic_qualification.qualification_suite_archive import (
    create_qualification_suite_archive,
    next_qualification_suite_run_id,
    qualification_archives_for_suite,
)
from standards_atlas.application.workflow import (
    EndToEndWorkflowService,
    QualificationWorkflowPlanner,
    RoutedQualificationWorkflowPlanner,
    WorkflowManifestLoader,
    WorkflowManifestType,
    WorkflowPlan,
    WorkflowRunReporter,
    WorkflowStage,
    WorkflowTask,
    load_qualification_suite_manifest,
    parse_manifest_options,
)
from standards_atlas.application.workspace import WorkspaceLayout
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import catalog_app, workflow_app
from standards_atlas.cli.composition import build_workflow_service


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
            help="Regenerate Docling and downstream artifacts for qualification.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Regenerate derived artifacts; qualification also recomputes its matrix.",
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
        int, typer.Option("--corpus-count", min=1, help="Qualification corpus size.")
    ] = 500,
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
        keep=tuple(keep or ()),
        corpus_count=corpus_count,
        corpus_strategy=corpus_strategy,
        corpus_seed=corpus_seed,
        knowledge_domain=knowledge_domain,
        corpus_output=corpus_output,
        qualification_output=qualification_output,
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
            help="Regenerate Docling and downstream artifacts for qualification.",
        ),
    ] = cli_defaults.DEFAULT_FALSE,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Regenerate derived artifacts; qualification also recomputes its matrix.",
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
        int, typer.Option("--corpus-count", min=1, help="Qualification corpus size.")
    ] = 500,
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
        keep=tuple(keep or ()),
        corpus_count=corpus_count,
        corpus_strategy=corpus_strategy,
        corpus_seed=corpus_seed,
        knowledge_domain=knowledge_domain,
        corpus_output=corpus_output,
        qualification_output=qualification_output,
    )
    suite_run_id: str | None = None
    suite_manifest_path: Path | None = None
    routing_manifest_path: Path | None = None
    if task is WorkflowTask.ROUTED_QUALIFICATION:
        resolved = WorkflowManifestLoader().load(parse_manifest_options(tuple(manifests)))
        suite_manifest_path = resolved.optional(WorkflowManifestType.QUALIFICATION_SUITE)
        assert suite_manifest_path is not None
        suite = load_qualification_suite_manifest(suite_manifest_path)
        routing_manifest_path, _ = suite.resolve(suite_manifest_path, Path.cwd())
        archive_directory = Path("local/evaluation")
        suite_run_id = next_qualification_suite_run_id(archive_directory)
        plan = _with_suite_run_id(plan, suite_run_id)

    # Scratch artifacts are retained after a run for debugging but never reused
    # implicitly by a subsequent workflow execution.
    WorkspaceLayout(Path.cwd()).clear_work()
    service = build_workflow_service(Path.cwd())
    result = service.execute(
        plan,
        project_root=Path.cwd(),
        continue_after_review=continue_after_review,
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
        if suite_run_id is not None:
            assert suite_manifest_path is not None
            assert routing_manifest_path is not None
            archive_directory = Path("local/evaluation")
            suite_archive = create_qualification_suite_archive(
                archive_directory=archive_directory,
                suite_run_id=suite_run_id,
                suite_manifest_path=suite_manifest_path,
                routing_manifest_path=routing_manifest_path,
                qualification_archives=qualification_archives_for_suite(
                    archive_directory, suite_run_id
                ),
            )
            typer.echo(f"Suite analysis archive  : {suite_archive}")
        return

    typer.echo(f"Workflow paused         : {len(result.executed_steps)} steps executed")
    if result.blocked_documents:
        typer.echo("Review required for     : " + ", ".join(result.blocked_documents))
    if result.blocked_families:
        typer.echo("AtlasData review for    : " + ", ".join(result.blocked_families))
    typer.echo("Continue after completing the reviews with --continue-after-review.")


def _with_suite_run_id(plan: WorkflowPlan, suite_run_id: str) -> WorkflowPlan:
    """Correlate all qualification matrix subprocesses in one suite invocation."""

    steps = tuple(
        replace(step, command=(*step.command, "--suite-run-id", suite_run_id))
        if step.stage is WorkflowStage.QUALIFICATION_MATRIX
        else step
        for step in plan.steps
    )
    return replace(plan, steps=steps)


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
    keep: tuple[WorkflowStage, ...],
    corpus_count: int,
    corpus_strategy: SamplingStrategy,
    corpus_seed: int,
    knowledge_domain: str,
    corpus_output: Path,
    qualification_output: Path,
) -> WorkflowPlan:
    if force and overwrite:
        raise typer.BadParameter("--force and --overwrite are mutually exclusive")
    if keep and not overwrite:
        raise typer.BadParameter("--keep requires --overwrite")
    if task is WorkflowTask.DOCUMENTS and regenerate_docling:
        raise typer.BadParameter("--regenerate-docling is only valid for --task qualification")
    if task in {WorkflowTask.QUALIFICATION, WorkflowTask.ROUTED_QUALIFICATION} and force:
        raise typer.BadParameter(
            "--force is only valid for --task documents; use --regenerate-docling or --overwrite"
        )

    try:
        resolved = WorkflowManifestLoader().load(parse_manifest_options(manifests))
        standards_manifest = resolved.require(WorkflowManifestType.STANDARDS)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    qualification_manifest = resolved.optional(WorkflowManifestType.QUALIFICATION_MATRIX)
    routing_manifest = resolved.optional(WorkflowManifestType.ROUTING_CONTRACT)
    qualification_suite = resolved.optional(WorkflowManifestType.QUALIFICATION_SUITE)
    if task is WorkflowTask.QUALIFICATION and qualification_manifest is None:
        raise typer.BadParameter(
            "--task qualification requires a manifest of type 'qualification_matrix'"
        )
    if task is WorkflowTask.ROUTED_QUALIFICATION and qualification_suite is None:
        raise typer.BadParameter(
            "--task routed-qualification requires a manifest of type 'qualification_suite'"
        )
    model = YamlStandardCatalogReader().read(standards_manifest)
    keys = (
        model.doorstop_hierarchy(hierarchy).families
        if hierarchy is not None
        else _select_manifest_families(model, family, profile, all_families)
    )
    if task is WorkflowTask.DOCUMENTS:
        return EndToEndWorkflowService().plan(
            model,
            family_keys=keys,
            catalog_root=Path.cwd(),
            force=force or overwrite,
            keep_stages=keep,
            hierarchy_key=hierarchy,
            routing_manifest_path=routing_manifest,
        )

    if task is WorkflowTask.ROUTED_QUALIFICATION:
        assert qualification_suite is not None
        try:
            routed = RoutedQualificationWorkflowPlanner().plan(
                model,
                family_keys=keys,
                catalog_root=Path.cwd(),
                suite_manifest_path=qualification_suite,
                corpus_count=corpus_count,
                corpus_strategy=corpus_strategy,
                corpus_seed=corpus_seed,
                knowledge_domain=knowledge_domain,
                hierarchy_key=hierarchy,
                regenerate_docling=regenerate_docling,
                overwrite=overwrite or regenerate_docling,
                keep_stages=keep,
                corpus_output=corpus_output,
                qualification_output=qualification_output,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        return WorkflowPlan(
            families=routed.document_plan.families,
            steps=routed.steps,
            force=routed.document_plan.force,
            kept_stages=routed.document_plan.kept_stages,
        )

    assert qualification_manifest is not None
    qualification = QualificationWorkflowPlanner().plan(
        model,
        family_keys=keys,
        catalog_root=Path.cwd(),
        manifest_path=qualification_manifest,
        corpus_count=corpus_count,
        corpus_strategy=corpus_strategy,
        corpus_seed=corpus_seed,
        knowledge_domain=knowledge_domain,
        hierarchy_key=hierarchy,
        regenerate_docling=regenerate_docling,
        overwrite=overwrite or regenerate_docling,
        keep_stages=keep,
        corpus_output=corpus_output,
        qualification_output=qualification_output,
        routing_manifest_path=routing_manifest,
    )
    return WorkflowPlan(
        families=qualification.document_plan.families,
        steps=qualification.steps,
        force=qualification.document_plan.force,
        kept_stages=qualification.document_plan.kept_stages,
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
