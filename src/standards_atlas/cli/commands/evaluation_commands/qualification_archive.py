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
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    APPLICABILITY_DETAIL_FAILURES_FILENAME,
    APPLICABILITY_DETAIL_REPORT_FILENAME,
    APPLICABILITY_DETAIL_SELECTION_FILENAME,
    build_applicability_detail_selection,
    load_applicability_detail_failure_report,
    load_applicability_detail_report,
    load_applicability_detail_selection,
    validate_applicability_detail_artifacts,
    validate_completed_applicability_detail_enrichment,
)
from standards_atlas.application.semantic_qualification.consensus import ConsensusReport
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
    qualification_snapshot_members,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_run_provenance import (
    validate_semantic_extraction_qualification_provenance,
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
    """Create the final run archive after all enabled qualification stages."""
    manifest = QualificationMatrixManifest.load(manifest_path)
    run_directory = output / manifest.matrix_id
    metrics_path = run_directory / "qualification-analysis-metrics.json"
    analysis_metrics: dict[str, Any] | None = None
    if manifest.consensus.enabled:
        if not metrics_path.is_file():
            raise typer.BadParameter(f"qualification analysis metrics not found: {metrics_path}")
        analysis_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    selection_path = run_directory / QUALIFICATION_SELECTION_FILENAME
    if not selection_path.is_file():
        raise typer.BadParameter(f"qualification clause selection not found: {selection_path}")
    run_selection = load_qualification_run_selection(selection_path)
    ensure_qualification_run_snapshots(
        selection_root=run_directory,
        selection=run_selection,
        corpus_root=corpus_root,
    )
    selected_examples = examples_for_persisted_selection(
        selection_root=run_directory,
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
    coverage = None
    if manifest.consensus.enabled:
        coverage_path = run_directory / QUALIFICATION_COVERAGE_FILENAME
        if not coverage_path.is_file():
            raise typer.BadParameter(f"qualification coverage not found: {coverage_path}")
        coverage = load_qualification_coverage(coverage_path)
        selected_coordinates = {
            (item.document_key, item.clause_id) for item in run_selection.clauses
        }
        coverage_coordinates = {(item.document_key, item.clause_id) for item in coverage.clauses}
        if coverage_coordinates != selected_coordinates:
            missing = selected_coordinates - coverage_coordinates
            unexpected = coverage_coordinates - selected_coordinates
            details: list[str] = []
            if missing:
                details.append(f"missing={len(missing)}")
            if unexpected:
                details.append(f"unexpected={len(unexpected)}")
            raise typer.BadParameter(
                "qualification coverage does not match the persisted run selection"
                + (f" ({', '.join(details)})" if details else "")
            )
        qualified_coordinates = {
            (item.document_key, item.clause_id)
            for item in coverage.clauses
            if item.status == "qualified"
        }
        unqualified_coordinates = {
            (item.document_key, item.clause_id)
            for item in coverage.clauses
            if item.status == "unqualified"
        }
        if qualified_coordinates & unqualified_coordinates:
            raise typer.BadParameter(
                "qualification coverage contains clauses with conflicting qualification status"
            )
        if qualified_coordinates | unqualified_coordinates != selected_coordinates:
            raise typer.BadParameter(
                "qualification coverage does not account for the persisted run selection"
            )
        assert analysis_metrics is not None
        qualified_clause_count = analysis_metrics.get(
            "qualified_clause_count", analysis_metrics.get("clause_count")
        )
        if qualified_clause_count != coverage.qualified_clause_count:
            raise typer.BadParameter(
                "qualification metrics disagree with persisted qualification coverage: "
                f"{qualified_clause_count} vs {coverage.qualified_clause_count} qualified clauses"
            )
        if coverage.accounted_clause_count != run_selection.selected_clause_count:
            raise typer.BadParameter(
                "qualification coverage does not account for the persisted run selection: "
                f"{coverage.accounted_clause_count}/{run_selection.selected_clause_count} clauses"
            )
    matrix_report_path = run_directory / "qualification-matrix.json"
    matrix_passed = None
    if matrix_report_path.is_file():
        matrix_report = json.loads(matrix_report_path.read_text(encoding="utf-8"))
        matrix_passed = matrix_report.get("passed")

    detail_summary: dict[str, Any] | None = None
    detail_consensus_path: Path | None = None
    detail_config = manifest.applicability_detail_enrichment
    if detail_config.enabled:
        if coverage is None:
            raise typer.BadParameter(
                "applicability detail enrichment requires consensus qualification coverage"
            )
        detail_consensus_path = (
            manifest.consensus.output_directory / manifest.matrix_id / "consensus-report.json"
        )
        if not detail_consensus_path.is_file():
            raise typer.BadParameter(
                f"final qualification consensus not found: {detail_consensus_path}"
            )
        consensus = ConsensusReport.model_validate_json(
            detail_consensus_path.read_text(encoding="utf-8")
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

        detail_selection_path = run_directory / APPLICABILITY_DETAIL_SELECTION_FILENAME
        detail_report_path = run_directory / APPLICABILITY_DETAIL_REPORT_FILENAME
        detail_failures_path = run_directory / APPLICABILITY_DETAIL_FAILURES_FILENAME
        for label, path in (
            ("selection", detail_selection_path),
            ("report", detail_report_path),
            ("failure report", detail_failures_path),
        ):
            if not path.is_file():
                raise typer.BadParameter(
                    f"applicability detail {label} not found; run "
                    f"applicability-detail-enrich first: {path}"
                )
        if detail_config.model is None:
            raise typer.BadParameter("applicability detail enrichment has no configured model")
        detail_model = next(
            (item for item in manifest.models if item.id == detail_config.model),
            None,
        )
        if detail_model is None or not detail_model.model_ref:
            raise typer.BadParameter(
                "applicability detail enrichment model is absent or incomplete in the manifest"
            )
        try:
            expected_detail_selection = build_applicability_detail_selection(
                run_selection=run_selection,
                examples=selected_examples,
                consensus=consensus,
                coverage=coverage,
                task_version=detail_config.task_version,
            )
            detail_selection = load_applicability_detail_selection(detail_selection_path)
            detail_report = load_applicability_detail_report(detail_report_path)
            detail_failures = load_applicability_detail_failure_report(detail_failures_path)
            summary = validate_completed_applicability_detail_enrichment(
                expected_selection=expected_detail_selection,
                persisted_selection=detail_selection,
                report=detail_report,
                failures=detail_failures,
                config=detail_config,
                model_id=detail_model.id,
                model_ref=detail_model.model_ref,
            )
            validate_applicability_detail_artifacts(
                artifact_root=run_directory / "applicability-detail",
                selection=detail_selection,
                report=detail_report,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        detail_summary = summary.model_dump(mode="json")

    semantic_report_path = run_directory / "semantic-extraction-qualification.json"
    semantic_report: dict[str, Any] | None = None
    if manifest.semantic_extraction_qualification.enabled:
        if not semantic_report_path.is_file():
            raise typer.BadParameter(
                f"semantic extraction qualification report not found: {semantic_report_path}"
            )
        semantic_report = json.loads(semantic_report_path.read_text(encoding="utf-8"))
        try:
            validate_semantic_extraction_qualification_provenance(
                semantic_report,
                run_directory=run_directory,
                selection=run_selection,
                config=manifest.semantic_extraction_qualification,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        selected_count = semantic_report.get("selected_clause_count")
        context_count = semantic_report.get("eligibility_context_clause_count")
        if selected_count != run_selection.selected_clause_count:
            raise typer.BadParameter(
                "semantic extraction qualification selection differs from matrix selection: "
                f"{selected_count} vs {run_selection.selected_clause_count} clauses"
            )
        if coverage is None:
            raise typer.BadParameter(
                "semantic extraction qualification requires consensus qualification coverage"
            )
        if context_count != coverage.qualified_clause_count:
            raise typer.BadParameter(
                "semantic extraction eligibility context disagrees with persisted qualification "
                f"coverage: {context_count}/{coverage.qualified_clause_count} qualified clauses"
            )

    core_paths = tuple(
        path
        for path in sorted(run_directory.rglob("*"))
        if path.is_file() and "cascade" not in path.relative_to(run_directory).parts
    )
    manifest_payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    input_members = [
        member
        for member in collect_qualification_input_members(
            manifest_payload=manifest_payload,
            resources=resources,
            corpus_root=corpus_root,
            published_corpus_root=published_corpus_root,
        )
        if member[1] not in {"inputs/corpus/dataset.json", "inputs/corpus/corpus.yaml"}
    ]
    input_members.extend(qualification_snapshot_members(run_directory, run_selection))
    input_members.extend(
        (
            (config, "inputs/runtime/llm-config.yaml"),
            (mcp_config, "inputs/runtime/mcp-config.yaml"),
        )
    )
    if detail_consensus_path is not None:
        input_members.append(
            (
                detail_consensus_path,
                "inputs/applicability-detail/final-consensus-report.json",
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
        applicability_detail_enrichment=detail_summary,
        semantic_extraction_qualification=semantic_report,
        archive_directory=archive_output,
        input_members=tuple(input_members),
    )
    typer.echo(f"Analysis archive         : {archive}")
