"""CLI for ontology-guided semantic extraction qualification."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.filesystem import (
    FileSystemEngineeringDocumentRepository,
    FileSystemSemanticExtractionRepository,
)
from standards_atlas.adapters.llm import (
    LlmConfig,
    OpenAICompatibleLlmGateway,
    RamaLamaServerManager,
)
from standards_atlas.adapters.llm.formal_semantic_extractor import OntologyGuidedLlmExtractor
from standards_atlas.application.evaluation.repository import EvaluationDatasetRepository
from standards_atlas.application.semantic_extraction import (
    ExtractionEligibilityContext,
    ExtractionProgress,
    SemanticExtractionService,
    extraction_eligibility,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_qualification import (
    qualify_semantic_extractions,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_selection import (
    selected_clause_ids_by_document,
)
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.domain.model import (
    ApplicabilityFunction,
    DocumentSemanticExtraction,
    KnowledgeKind,
)


@evaluation_app.command("semantic-extraction-qualification")
def qualify_semantic_extraction(
    manifest_path: Annotated[Path, typer.Option("--manifest", exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = Path(".atlas/data"),
    corpus_root: Annotated[Path, typer.Option("--corpus-root", file_okay=False)] = Path(
        ".atlas/data/evaluation/corpora"
    ),
    limit: Annotated[
        int | None, typer.Option("--limit", min=1, help="Limit clauses for this qualification run.")
    ] = None,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Regenerate selected semantic extractions with the LLM cache disabled.",
        ),
    ] = False,
    fail_on_qualification_failure: Annotated[
        bool,
        typer.Option(
            "--fail-on-qualification-failure/--no-fail-on-qualification-failure",
            help=(
                "Exit with status 1 when semantic extraction qualification fails; disable for "
                "orchestrated workflows that consume the report."
            ),
            show_default=True,
        ),
    ] = True,
) -> None:
    """Qualify persisted ontology-guided extraction artifacts for one matrix run."""
    manifest = QualificationMatrixManifest.load(manifest_path)
    config = manifest.semantic_extraction_qualification
    if not config.enabled:
        raise typer.BadParameter("semantic extraction qualification is disabled in the manifest")

    dataset = EvaluationDatasetRepository(corpus_root).load(manifest.task, manifest.dataset_version)
    selected_examples = dataset.examples[:limit] if limit is not None else dataset.examples
    selected_ids_by_document = selected_clause_ids_by_document(selected_examples)
    eligibility_contexts = _load_qualification_eligibility_contexts(output)

    root = workspace / "semantic-extractions"
    repository = FileSystemSemanticExtractionRepository(workspace)
    documents = FileSystemEngineeringDocumentRepository(workspace).list()
    contexts_by_document: dict[str, dict[str, ExtractionEligibilityContext]] = {}
    eligible_ids_by_document: dict[str, set[str]] = {}
    for document in documents:
        selected_ids = selected_ids_by_document.get(document.key.value)
        if not selected_ids:
            continue
        document_contexts = {
            clause_id: eligibility_contexts[(document.key.value, clause_id)]
            for clause_id in selected_ids
            if (document.key.value, clause_id) in eligibility_contexts
        }
        contexts_by_document[document.key.value] = document_contexts
        eligible_ids = {
            clause.id.value
            for clause in document.clauses
            if clause.id.value in selected_ids
            and (context := document_contexts.get(clause.id.value)) is not None
            and extraction_eligibility(clause, context=context).eligible
        }
        eligible_ids_by_document[document.key.value] = eligible_ids

    pending_ids_by_document: dict[str, frozenset[str]] = {}
    for document_key, selected_ids in eligible_ids_by_document.items():
        existing = repository.load(document_key)
        existing_ids = (
            {item.clause_id for item in existing.clauses} if existing is not None else set()
        )
        pending_ids_by_document[document_key] = (
            frozenset(selected_ids) if fresh else frozenset(selected_ids.difference(existing_ids))
        )

    resolved_model: str | None = config.model
    resolved_provider: str | None = None
    if config.generate_missing:
        llm_config = LlmConfig.load(None)
        llm_config = replace(llm_config, timeout_seconds=config.timeout_seconds)
        if fresh:
            llm_config = replace(llm_config, cache_directory=None)
        model_candidate = _resolve_extraction_model(manifest, config.model)
        if model_candidate is not None:
            if model_candidate.provider != "ramalama":
                raise typer.BadParameter(
                    "semantic extraction qualification currently requires a ramalama model; "
                    f"got {model_candidate.provider!r} for {model_candidate.id}"
                )
            if not model_candidate.model_ref:
                raise typer.BadParameter(
                    f"semantic extraction model {model_candidate.id!r} has no model_ref"
                )
            resolved_model = model_candidate.id
            resolved_provider = model_candidate.provider
            llm_config = replace(
                llm_config,
                model=model_candidate.model_ref,
                server=replace(llm_config.server, model=model_candidate.model_ref),
            )
            gateway_model = model_candidate.model_ref
        else:
            resolved_model = config.model or llm_config.model
            resolved_provider = "ramalama"
            gateway_model = llm_config.model

        server = RamaLamaServerManager(llm_config)
        try:
            if llm_config.server.enabled:
                server.start()
            gateway = OpenAICompatibleLlmGateway(llm_config)
            extractor = OntologyGuidedLlmExtractor(
                gateway,
                model=gateway_model,
            )
            service = SemanticExtractionService(extractor)
            progress_state = {"completed": 0, "ok": 0, "failed": 0, "timeout": 0}
            total_attempts = sum(len(ids) for ids in pending_ids_by_document.values())

            def report_progress(event: ExtractionProgress) -> None:
                current = progress_state["completed"] + 1
                human_clause = event.clause_reference
                if event.clause_title:
                    human_clause += f" — {event.clause_title}"
                prefix = (
                    f"[Semantic extraction {current:02d}/{total_attempts:02d}] "
                    f"{human_clause} ({event.document_key}/{event.clause_id})"
                )
                if event.phase == "started":
                    typer.echo(f"{prefix} started")
                    return
                progress_state["completed"] += 1
                duration = event.duration_seconds or 0.0
                if event.status == "ok":
                    progress_state["ok"] += 1
                    typer.echo(
                        f"{prefix} ok entities={event.entity_count} "
                        f"relations={event.relation_count} elapsed={duration:.1f}s"
                    )
                    return
                progress_state["failed"] += 1
                if event.status == "timeout":
                    progress_state["timeout"] += 1
                typer.echo(f"{prefix} {event.status} elapsed={duration:.1f}s")

            for document in documents:
                selected_ids = eligible_ids_by_document.get(document.key.value)
                if not selected_ids:
                    continue
                existing = repository.load(document.key.value)
                existing_by_id = (
                    {item.clause_id: item for item in existing.clauses}
                    if existing is not None
                    else {}
                )
                extraction_ids = pending_ids_by_document.get(document.key.value, frozenset())
                if extraction_ids:
                    generated = service.extract_document(
                        document,
                        ontology_versions=config.ontology_versions,
                        clause_ids=extraction_ids,
                        eligibility_by_clause=contexts_by_document.get(document.key.value, {}),
                        progress=report_progress,
                    )
                    merged = {
                        **existing_by_id,
                        **{item.clause_id: item for item in generated.clauses},
                    }
                    existing_failures = (
                        {item.clause_id: item for item in existing.failures}
                        if existing is not None
                        else {}
                    )
                    if fresh:
                        for clause_id in extraction_ids:
                            existing_failures.pop(clause_id, None)
                    merged_failures = {
                        **existing_failures,
                        **{item.clause_id: item for item in generated.failures},
                    }
                    for clause_id in generated.clauses:
                        merged_failures.pop(clause_id.clause_id, None)
                    repository.save(
                        DocumentSemanticExtraction(
                            source_document_key=document.key.value,
                            clauses=tuple(merged[key] for key in sorted(merged)),
                            failures=tuple(merged_failures[key] for key in sorted(merged_failures)),
                        )
                    )
            typer.echo(
                "Semantic extraction     : "
                f"ok={progress_state['ok']} failed={progress_state['failed']} "
                f"timeouts={progress_state['timeout']}"
            )
        finally:
            if llm_config.server.enabled:
                server.stop()

    extractions = []
    if root.is_dir():
        for document_key, selected_ids in sorted(eligible_ids_by_document.items()):
            loaded = repository.load(document_key)
            if loaded is None:
                continue
            selected_clauses = tuple(
                item for item in loaded.clauses if item.clause_id in selected_ids
            )
            selected_failures = tuple(
                item for item in loaded.failures if item.clause_id in selected_ids
            )
            if selected_clauses or selected_failures:
                extractions.append(
                    loaded.model_copy(
                        update={"clauses": selected_clauses, "failures": selected_failures}
                    )
                )

    selected_clause_count = len(selected_examples)
    eligibility_context_clause_count = sum(
        1
        for document_key, clause_ids in selected_ids_by_document.items()
        for clause_id in clause_ids
        if (document_key, clause_id) in eligibility_contexts
    )
    eligible_clause_count = sum(len(ids) for ids in eligible_ids_by_document.values())
    report = qualify_semantic_extractions(
        tuple(extractions),
        config,
        expected_clause_count=selected_clause_count,
        selected_clause_count=selected_clause_count,
        eligibility_context_clause_count=eligibility_context_clause_count,
        eligible_clause_count=eligible_clause_count,
        extraction_model=resolved_model,
        extraction_provider=resolved_provider,
    )
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "semantic-extraction-qualification.json"
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Semantic extraction model: {report.extraction_model or 'unknown'}")
    typer.echo(f"Semantic extraction provider: {report.extraction_provider or 'unknown'}")
    typer.echo(f"Selected clauses         : {report.selected_clause_count}")
    typer.echo(f"Eligibility contexts     : {report.eligibility_context_clause_count}")
    typer.echo(f"Eligible clauses         : {report.eligible_clause_count}")
    typer.echo(f"Attempted clauses        : {report.attempted_clause_count}")
    typer.echo(f"Extracted clauses        : {report.extracted_clause_count}")
    typer.echo(f"Skipped clauses          : {report.skipped_clause_count}")
    typer.echo(f"Semantic extraction docs : {report.documents}")
    typer.echo(f"Ontology conformance     : {report.ontology_conformance:.3f}")
    typer.echo(f"Ontology violations      : {report.ontology_violation_count}")
    typer.echo(f"Extraction failures      : {report.extraction_failure_count}")
    typer.echo(f"Timeouts                 : {report.timeout_count}")
    for failure in report.extraction_failures:
        human_reference = failure.get("clause_reference") or (
            f"{failure['document_key']}/{failure['clause_id']}"
        )
        title = failure.get("clause_title")
        if title:
            human_reference += f" — {title}"
        typer.echo(
            f"  - {human_reference} [{failure['clause_id']}]: "
            f"{failure['kind']} ({failure['error_type']})"
        )
    if report.ontology_violations:
        for violation in report.ontology_violations:
            typer.echo(f"  - {violation.kind}: {violation.term} ({violation.count})")
    typer.echo(
        "Gold scoring             : "
        + (f"{report.gold_scored_items} cases" if report.gold_available else "unscored")
    )
    typer.echo(f"Report                   : {report_path}")
    if not report.passed and fail_on_qualification_failure:
        raise typer.Exit(code=1)


def _resolve_extraction_model(manifest: QualificationMatrixManifest, model_id: str | None):
    """Resolve a semantic-extraction model id through the qualification model catalog."""
    if model_id is None:
        return None
    candidate = next((model for model in manifest.models if model.id == model_id), None)
    if candidate is None:
        raise typer.BadParameter(
            f"semantic extraction model {model_id!r} is not declared in manifest.models"
        )
    return candidate


def _selected_clause_ids_by_document(examples):
    """Compatibility wrapper around the shared dataset coordinate resolver."""
    return selected_clause_ids_by_document(examples)


def _load_qualification_eligibility_contexts(
    output: Path,
) -> dict[tuple[str, str], ExtractionEligibilityContext]:
    """Load the latest matrix consensus for each clause as extraction context."""
    provenance_path = output / "cascade-provenance.json"
    if not provenance_path.is_file():
        return {}
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    stage_ids = [
        str(stage["stage_id"])
        for stage in provenance.get("stages", [])
        if isinstance(stage, dict) and stage.get("stage_id")
    ]
    contexts: dict[tuple[str, str], ExtractionEligibilityContext] = {}
    for stage_id in stage_ids:
        report_path = output / "cascade" / stage_id / "consensus-report.json"
        if not report_path.is_file():
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for clause in report.get("clauses", []):
            if not isinstance(clause, dict):
                continue
            document_key = clause.get("document_key")
            clause_id = clause.get("clause_id")
            if not isinstance(document_key, str) or not isinstance(clause_id, str):
                continue
            contexts[(document_key, clause_id)] = _eligibility_context_from_consensus(clause)
    return contexts


def _eligibility_context_from_consensus(
    clause: dict[str, object],
) -> ExtractionEligibilityContext:
    knowledge_values = clause.get("proposed_knowledge_kinds")
    if not isinstance(knowledge_values, list):
        primary = clause.get("primary_knowledge_kind")
        knowledge_values = [primary] if isinstance(primary, str) else []
    knowledge_kinds = tuple(
        kind
        for value in knowledge_values
        if isinstance(value, str)
        for kind in _parse_enum(KnowledgeKind, value)
    )
    applicability_values = clause.get("proposed_applicability_functions")
    applicability_functions = tuple(
        function
        for value in (applicability_values if isinstance(applicability_values, list) else [])
        if isinstance(value, str)
        for function in _parse_enum(ApplicabilityFunction, value)
    )
    return ExtractionEligibilityContext(
        knowledge_kinds=knowledge_kinds,
        applicability_present=bool(clause.get("applicability_present", False)),
        applicability_functions=applicability_functions,
        role_semantics_present=bool(clause.get("role_semantics_present", False)),
    )


def _parse_enum(enum_type, value: str):
    try:
        return (enum_type(value),)
    except ValueError:
        return ()
