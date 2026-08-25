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
from standards_atlas.application.semantic_extraction import SemanticExtractionService
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_qualification import (
    qualify_semantic_extractions,
)
from standards_atlas.cli.apps import evaluation_app


@evaluation_app.command("semantic-extraction-qualification")
def qualify_semantic_extraction(
    manifest_path: Annotated[Path, typer.Option("--manifest", exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    workspace: Annotated[Path, typer.Option("--workspace", file_okay=False)] = Path(".atlas/data"),
) -> None:
    """Qualify persisted ontology-guided extraction artifacts for one matrix run."""
    manifest = QualificationMatrixManifest.load(manifest_path)
    config = manifest.semantic_extraction_qualification
    if not config.enabled:
        raise typer.BadParameter("semantic extraction qualification is disabled in the manifest")

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
            if repository.load(document.key.value) is None:
                repository.save(
                    service.extract_document(document, ontology_versions=config.ontology_versions)
                )

    extractions = []
    if root.is_dir():
        for path in sorted(root.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            extraction = payload.get("extraction")
            if isinstance(extraction, dict):
                document_key = extraction.get("source_document_key")
                if isinstance(document_key, str):
                    loaded = repository.load(document_key)
                    if loaded is not None:
                        extractions.append(loaded)

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
