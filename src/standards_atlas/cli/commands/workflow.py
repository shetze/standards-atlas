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
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Run qualification LLM inference without proposal reuse or response cache.",
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
        keep=tuple(keep or ()),
        corpus_count=corpus_count,
        limit=limit,
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
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Run qualification LLM inference without proposal reuse or response cache.",
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
        keep=tuple(keep or ()),
        corpus_count=corpus_count,
        limit=limit,
        corpus_strategy=corpus_strategy,
        corpus_seed=corpus_seed,
        knowledge_domain=knowledge_domain,
        corpus_output=corpus_output,
        qualification_output=qualification_output,
    )
    # Keep cross-invocation workflow checkpoints so an interrupted workflow can
    # resume from the first incomplete step. Other scratch state is disposable.
    WorkspaceLayout(Path.cwd()).clear_work(preserve_workflow=True)
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
    keep: tuple[WorkflowStage, ...],
    corpus_count: int,
    limit: int | None,
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
    if task is WorkflowTask.DOCUMENTS and limit is not None:
        raise typer.BadParameter("--limit is only valid for --task qualification")
    if task is WorkflowTask.DOCUMENTS and fresh:
        raise typer.BadParameter("--fresh is only valid for --task qualification")
    if task is WorkflowTask.QUALIFICATION and force:
        raise typer.BadParameter(
            "--force is only valid for --task documents; use --regenerate-docling or --overwrite"
        )

    try:
        resolved = WorkflowManifestLoader().load(parse_manifest_options(manifests))
        standards_manifest = resolved.require(WorkflowManifestType.STANDARDS)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    qualification_manifest = resolved.optional(WorkflowManifestType.QUALIFICATION_MATRIX)
    if task is WorkflowTask.QUALIFICATION and qualification_manifest is None:
        raise typer.BadParameter(
            "--task qualification requires a manifest of type 'qualification_matrix'"
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
        )

    assert qualification_manifest is not None
    qualification = QualificationWorkflowPlanner().plan(
        model,
        family_keys=keys,
        catalog_root=Path.cwd(),
        manifest_path=qualification_manifest,
        corpus_count=corpus_count,
        limit=limit,
        corpus_strategy=corpus_strategy,
        corpus_seed=corpus_seed,
        knowledge_domain=knowledge_domain,
        hierarchy_key=hierarchy,
        regenerate_docling=regenerate_docling,
        overwrite=overwrite or regenerate_docling,
        fresh=fresh,
        keep_stages=keep,
        corpus_output=corpus_output,
        qualification_output=qualification_output,
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
