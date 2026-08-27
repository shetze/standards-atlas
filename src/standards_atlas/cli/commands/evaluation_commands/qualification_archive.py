"""Finalize one immutable qualification-run archive after all workflow stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from standards_atlas.adapters.filesystem import FileSystemSemanticExtractionRepository
from standards_atlas.application.formal_semantics.resource_repository import (
    ResourceFormalOntologyRepository,
)
from standards_atlas.application.semantic_qualification.analysis_archive import (
    collect_qualification_input_members,
    create_analysis_archive,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QUALIFICATION_SELECTION_FILENAME,
    examples_for_persisted_selection,
    load_qualification_run_selection,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_selection import (
    selected_clause_ids_by_document,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("qualification-archive")
def finalize_qualification_archive(
    manifest_path: Annotated[Path, typer.Option("--manifest", exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    archive_output: Annotated[Path, typer.Option("--archive-output", file_okay=False)] = Path(
        "local/evaluation"
    ),
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = Path(".atlas/data"),
    resources: Annotated[Path, typer.Option("--resources", file_okay=False)] = (
        cli_defaults.DEFAULT_EVALUATION_RESOURCES
    ),
    config: Annotated[Path, typer.Option("--config", exists=True, readable=True)] = (
        cli_defaults.DEFAULT_LLM_CONFIG
    ),
    mcp_config: Annotated[Path, typer.Option("--mcp-config", exists=True, readable=True)] = (
        cli_defaults.DEFAULT_MCP_CONFIG
    ),
    corpus_root: Annotated[Path, typer.Option("--corpus-root", file_okay=False)] = Path(
        ".atlas/data/evaluation/corpora"
    ),
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    published_corpus_root: Annotated[
        Path, typer.Option("--published-corpus-root", file_okay=False)
    ] = Path("data/evaluation/corpora"),
) -> None:
    """Create the final run archive after matrix and semantic extraction qualification."""
    manifest = QualificationMatrixManifest.load(manifest_path)
    run_directory = output / manifest.matrix_id
    metrics_path = run_directory / "qualification-analysis-metrics.json"
    if not metrics_path.is_file():
        raise typer.BadParameter(f"qualification analysis metrics not found: {metrics_path}")
    analysis_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    selection_path = run_directory / QUALIFICATION_SELECTION_FILENAME
    if not selection_path.is_file():
        raise typer.BadParameter(f"qualification clause selection not found: {selection_path}")
    run_selection = load_qualification_run_selection(selection_path)
    selected_examples = examples_for_persisted_selection(
        corpus_root=corpus_root,
        selection=run_selection,
    )
    if (
        run_selection.task != manifest.task
        or run_selection.dataset_version != manifest.dataset_version
    ):
        raise typer.BadParameter(
            "persisted qualification selection does not match the qualification manifest"
        )
    if limit is not None and run_selection.requested_limit != limit:
        raise typer.BadParameter(
            f"--limit {limit} does not match persisted qualification selection "
            f"({run_selection.requested_limit})"
        )
    qualified_clause_count = analysis_metrics.get("clause_count")
    if qualified_clause_count != run_selection.selected_clause_count:
        raise typer.BadParameter(
            "qualification result does not cover the persisted run selection: "
            f"{qualified_clause_count} qualified vs "
            f"{run_selection.selected_clause_count} selected clauses"
        )
    matrix_report_path = run_directory / "qualification-matrix.json"
    matrix_passed = None
    if matrix_report_path.is_file():
        matrix_report = json.loads(matrix_report_path.read_text(encoding="utf-8"))
        matrix_passed = matrix_report.get("passed")

    semantic_report_path = run_directory / "semantic-extraction-qualification.json"
    semantic_report: dict[str, Any] | None = None
    if manifest.semantic_extraction_qualification.enabled:
        if not semantic_report_path.is_file():
            raise typer.BadParameter(
                f"semantic extraction qualification report not found: {semantic_report_path}"
            )
        semantic_report = json.loads(semantic_report_path.read_text(encoding="utf-8"))
        selected_count = semantic_report.get("selected_clause_count")
        context_count = semantic_report.get("eligibility_context_clause_count")
        if selected_count != run_selection.selected_clause_count:
            raise typer.BadParameter(
                "semantic extraction qualification selection differs from matrix selection: "
                f"{selected_count} vs {run_selection.selected_clause_count} clauses"
            )
        if context_count != run_selection.selected_clause_count:
            raise typer.BadParameter(
                "semantic extraction eligibility context is incomplete for the persisted run "
                f"selection: {context_count}/{run_selection.selected_clause_count} clauses"
            )

    core_paths = tuple(
        path
        for path in sorted(run_directory.rglob("*"))
        if path.is_file() and "cascade" not in path.relative_to(run_directory).parts
    )
    manifest_payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    input_members = list(
        collect_qualification_input_members(
            manifest_payload=manifest_payload,
            resources=resources,
            corpus_root=corpus_root,
            published_corpus_root=published_corpus_root,
        )
    )
    input_members.extend(
        (
            (config, "inputs/runtime/llm-config.yaml"),
            (mcp_config, "inputs/runtime/mcp-config.yaml"),
        )
    )

    execution_policy = None
    provenance_path = run_directory / "cascade-provenance.json"
    if provenance_path.is_file():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        policy = provenance.get("execution_policy")
        if isinstance(policy, dict):
            execution_policy = policy

    if semantic_report is not None:
        formal_repository = ResourceFormalOntologyRepository()
        for reference in manifest.semantic_extraction_qualification.ontology_versions:
            ontology_id, version = reference.split("@", maxsplit=1)
            definition = formal_repository.load(ontology_id, version)
            base = (
                Path(__file__).parents[3]
                / "resources"
                / "formal_ontologies"
                / ontology_id
                / version
            )
            input_members.append(
                (
                    base / "ontology.yaml",
                    f"inputs/formal-ontologies/{ontology_id}/{version}/ontology.yaml",
                )
            )
            input_members.append(
                (
                    base / definition.resource,
                    f"inputs/formal-ontologies/{ontology_id}/{version}/{definition.resource}",
                )
            )

        selected_by_document = selected_clause_ids_by_document(selected_examples)
        repository = FileSystemSemanticExtractionRepository(workspace)
        snapshot_root = run_directory / "archive-inputs" / "semantic-extractions"
        snapshot_root.mkdir(parents=True, exist_ok=True)
        for document_key, clause_ids in sorted(selected_by_document.items()):
            extraction = repository.load(document_key)
            if extraction is None:
                continue
            filtered = extraction.model_copy(
                update={
                    "clauses": tuple(
                        item for item in extraction.clauses if item.clause_id in clause_ids
                    ),
                    "failures": tuple(
                        item for item in extraction.failures if item.clause_id in clause_ids
                    ),
                }
            )
            if not filtered.clauses and not filtered.failures:
                continue
            safe = (
                document_key.strip()
                .replace("/", "_")
                .replace("\\", "_")
                .replace(":", "_")
                .replace(" ", "_")
            )
            snapshot = snapshot_root / f"{safe}.json"
            snapshot.write_text(
                json.dumps(
                    {"schema_version": 1, "extraction": filtered.model_dump(mode="json")},
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            input_members.append((snapshot, f"semantic-extractions/{snapshot.name}"))

    archive = create_analysis_archive(
        output_directory=output,
        matrix_id=manifest.matrix_id,
        manifest_path=manifest_path,
        core_paths=core_paths,
        cascade_directory=run_directory / "cascade",
        analysis_metrics=analysis_metrics,
        matrix_passed=matrix_passed,
        execution_policy=execution_policy,
        semantic_extraction_qualification=semantic_report,
        archive_directory=archive_output,
        input_members=tuple(input_members),
    )
    typer.echo(f"Analysis archive         : {archive}")
