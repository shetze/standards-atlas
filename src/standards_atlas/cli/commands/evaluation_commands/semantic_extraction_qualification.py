"""CLI for ontology-guided semantic extraction qualification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.filesystem import (
    FileSystemEngineeringDocumentRepository,
    FileSystemSemanticExtractionRepository,
)
from standards_atlas.adapters.llm import LlmConfig, OpenAICompatibleLlmGateway
from standards_atlas.adapters.llm.formal_semantic_extractor import OntologyGuidedLlmExtractor
from standards_atlas.application.evaluation.repository import EvaluationDatasetRepository
from standards_atlas.application.semantic_extraction import SemanticExtractionService
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_qualification import (
    qualify_semantic_extractions,
)
from standards_atlas.cli.apps import evaluation_app
from standards_atlas.domain.model import DocumentSemanticExtraction


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
) -> None:
    """Qualify persisted ontology-guided extraction artifacts for one matrix run."""
    manifest = QualificationMatrixManifest.load(manifest_path)
    config = manifest.semantic_extraction_qualification
    if not config.enabled:
        raise typer.BadParameter("semantic extraction qualification is disabled in the manifest")

    dataset = EvaluationDatasetRepository(corpus_root).load(manifest.task, manifest.dataset_version)
    selected_examples = dataset.examples[:limit] if limit is not None else dataset.examples
    selected_clause_ids_by_document: dict[str, set[str]] = {}
    for example in selected_examples:
        document_key = example.input.get("document_key")
        clause_id = example.input.get("clause_id")
        if isinstance(document_key, str) and isinstance(clause_id, str):
            selected_clause_ids_by_document.setdefault(document_key, set()).add(clause_id)

    root = workspace / "semantic-extractions"
    repository = FileSystemSemanticExtractionRepository(workspace)
    if config.generate_missing:
        llm_config = LlmConfig.load(None)
        gateway = OpenAICompatibleLlmGateway(llm_config)
        extractor = OntologyGuidedLlmExtractor(
            gateway,
            model=config.model or llm_config.model,
        )
        service = SemanticExtractionService(extractor)
        documents = FileSystemEngineeringDocumentRepository(workspace).list()
        for document in documents:
            selected_ids = selected_clause_ids_by_document.get(document.key.value)
            if not selected_ids:
                continue
            existing = repository.load(document.key.value)
            existing_by_id = (
                {item.clause_id: item for item in existing.clauses} if existing is not None else {}
            )
            missing_ids = frozenset(selected_ids.difference(existing_by_id))
            if missing_ids:
                generated = service.extract_document(
                    document,
                    ontology_versions=config.ontology_versions,
                    clause_ids=missing_ids,
                )
                merged = {**existing_by_id, **{item.clause_id: item for item in generated.clauses}}
                repository.save(
                    DocumentSemanticExtraction(
                        source_document_key=document.key.value,
                        clauses=tuple(merged[key] for key in sorted(merged)),
                    )
                )

    extractions = []
    if root.is_dir():
        for document_key, selected_ids in sorted(selected_clause_ids_by_document.items()):
            loaded = repository.load(document_key)
            if loaded is None:
                continue
            selected_clauses = tuple(
                item for item in loaded.clauses if item.clause_id in selected_ids
            )
            extractions.append(loaded.model_copy(update={"clauses": selected_clauses}))

    report = qualify_semantic_extractions(tuple(extractions), config)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "semantic-extraction-qualification.json"
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Semantic extraction docs : {report.documents}")
    typer.echo(f"Ontology conformance     : {report.ontology_conformance:.3f}")
    typer.echo(
        "Gold scoring             : "
        + (f"{report.gold_scored_items} cases" if report.gold_available else "unscored")
    )
    typer.echo(f"Report                   : {report_path}")
    if not report.passed:
        raise typer.Exit(code=1)
