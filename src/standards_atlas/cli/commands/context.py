"""Read-only context discovery commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.context import ContextSelectionProfile
from standards_atlas.application.knowledge_proposal_extraction import (
    EvidenceGroundingRequest,
    inspect_context_evidence,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import context_app
from standards_atlas.cli.composition import build_subject_candidate_vocabulary_service
from standards_atlas.domain.model import DocumentKey


@context_app.command("subject-vocabulary")
def subject_vocabulary(
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            file_okay=False,
            help="Engineering-document workspace to inspect.",
        ),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            dir_okay=False,
            help="Write the complete subject-candidate vocabulary as JSON.",
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            min=0,
            help="Maximum number of frequent candidates to show; 0 shows none.",
        ),
    ] = 20,
) -> None:
    """Discover subject candidates from persisted AtlasData term headings."""
    vocabulary = build_subject_candidate_vocabulary_service(workspace).build()
    analysis = vocabulary.analysis

    typer.echo(f"Term clauses              : {analysis.term_clauses}")
    typer.echo(f"Accepted term clauses     : {analysis.accepted_term_clauses}")
    typer.echo(f"Ignored term containers   : {analysis.ignored_term_containers}")
    typer.echo(f"Missing term headings     : {analysis.missing_headings}")
    typer.echo(f"Unique candidates         : {analysis.unique_candidates}")
    typer.echo(f"Repeated candidates       : {analysis.repeated_candidates}")
    typer.echo(f"Cross-document candidates : {analysis.cross_document_candidates}")
    typer.echo(f"Extraction coverage       : {analysis.extraction_coverage:.1%}")

    if limit:
        ranked = sorted(
            vocabulary.candidates,
            key=lambda candidate: (
                -len(candidate.provenance),
                candidate.normalized_label,
            ),
        )[:limit]
        if ranked:
            typer.echo("\nMost frequent candidates")
            for candidate in ranked:
                typer.echo(
                    f"{len(candidate.provenance):>5}  "
                    f"{candidate.document_count:>3} docs  "
                    f"{candidate.normalized_label}"
                )

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(vocabulary.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        typer.echo(f"\nVocabulary JSON           : {output}")


@context_app.command("evidence-inspect")
def evidence_inspect(
    document_key: Annotated[
        str,
        typer.Option("--document-key", help="Persisted EngineeringDocument key."),
    ],
    clause_id: Annotated[
        str,
        typer.Option("--clause-id", help="Target clause id to inspect."),
    ],
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            exists=True,
            file_okay=False,
            readable=True,
            help="Engineering-document workspace to inspect.",
        ),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    grounding_requests: Annotated[
        Path | None,
        typer.Option(
            "--grounding-requests",
            exists=True,
            dir_okay=False,
            readable=True,
            help=(
                "Optional JSON array of current EvidenceGroundingRequest objects. "
                "The declared source_ref must name a selected package source."
            ),
        ),
    ] = None,
    character_budget: Annotated[
        int,
        typer.Option("--character-budget", min=1, help="Deterministic context character budget."),
    ] = 12_000,
    max_sequence_distance: Annotated[
        int,
        typer.Option(
            "--max-sequence-distance",
            min=0,
            help="Maximum ordinary same-parent sequence distance considered by selection.",
        ),
    ] = 4,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            dir_okay=False,
            help="Destination deterministic, text-free inspection JSON.",
        ),
    ] = Path("local/evaluation/context-evidence-inspection.json"),
) -> None:
    """Inspect source selection, package fingerprints and grounding without a model call."""

    try:
        repository = FileSystemEngineeringDocumentRepository(workspace)
        document = repository.load(DocumentKey(value=document_key))
        matches = [clause for clause in document.clauses if clause.id.value == clause_id]
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one clause {clause_id!r} in document {document_key!r}, "
                f"found {len(matches)}"
            )
        requests = _load_grounding_requests(grounding_requests)
        report = inspect_context_evidence(
            document,
            matches[0],
            profile=ContextSelectionProfile(
                character_budget=character_budget,
                max_sequence_distance=max_sequence_distance,
            ),
            grounding_requests=requests,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                report.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    complete_grounding = sum(item.complete for item in report.grounding_results)
    grounding_failures = sum(len(item.failures) for item in report.grounding_results)
    typer.echo(f"Inspection contract       : {report.contract_id}")
    typer.echo(f"Target                    : {report.document_key} / {report.target_clause_id}")
    typer.echo(f"Selection completeness    : {report.selection_completeness}")
    typer.echo(
        "Sources                   : "
        f"{len(report.selected_sources)} selected / {len(report.omitted_sources)} omitted"
    )
    typer.echo(f"Known gaps                : {len(report.gaps)}")
    typer.echo(
        "Budget                    : "
        f"{report.budget['used_chars']} / {report.budget['configured_chars']} chars"
    )
    typer.echo(f"Package SHA-256           : {report.package_sha256}")
    typer.echo(
        "Grounding                : "
        f"{complete_grounding}/{len(report.grounding_results)} complete, "
        f"{grounding_failures} failure(s)"
    )
    typer.echo("Model execution           : no")
    typer.echo("Semantic quality assessed : no")
    typer.echo(f"Inspection JSON           : {output}")


def _load_grounding_requests(path: Path | None) -> tuple[EvidenceGroundingRequest, ...]:
    if path is None:
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return TypeAdapter(tuple[EvidenceGroundingRequest, ...]).validate_python(payload)
