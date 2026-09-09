"""Explicit public AtlasData export/restore; never run implicitly by qualification."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer
import yaml

from standards_atlas.adapters.atlasdata.knowledge_contract import AtlasDataKnowledgeReport
from standards_atlas.adapters.atlasdata.knowledge_evidence import atomic_write
from standards_atlas.adapters.atlasdata.knowledge_transfer import AtlasDataKnowledgeService
from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.catalog.atlasdata_binding import atlasdata_bindings
from standards_atlas.cli.apps import atlasdata_app
from standards_atlas.domain.model import DocumentKey

ManifestOption = Annotated[Path, typer.Option("--manifest", help="Standards manifest.")]
RootOption = Annotated[
    Path,
    typer.Option("--root", help="Project root for manifest-relative paths."),
]
WorkspaceOption = Annotated[Path, typer.Option("--workspace", help="Canonical workspace.")]
DocumentsOption = Annotated[
    list[str] | None,
    typer.Option("--document", help="Physical key; repeatable."),
]
FamiliesOption = Annotated[
    list[str] | None,
    typer.Option("--family", help="Manifest family; repeatable."),
]
EvidenceOption = Annotated[
    Path | None,
    typer.Option(
        "--evidence-root",
        help="Private evidence store; defaults to <workspace>/knowledge-evidence.",
    ),
]
ReportOption = Annotated[
    Path | None,
    typer.Option("--output", help="Optional local JSON change report."),
]
WriteOption = Annotated[
    bool,
    typer.Option("--write", help="Perform the explicit writes after preflight."),
]


def _run(
    *,
    exporting: bool,
    manifest: Path,
    root: Path,
    workspace: Path,
    document: Sequence[str] | None,
    family: Sequence[str] | None,
    evidence_root: Path | None,
    output: Path | None,
    write: bool,
    dimensions: Sequence[str] = (),
    clause_ids: Sequence[str] = (),
    strict_evidence: bool = False,
    available_only: bool = False,
) -> None:
    try:
        root = root.resolve()
        manifest = (root / manifest).resolve()
        workspace = (root / workspace).resolve()
        evidence_root = (
            (root / evidence_root).resolve() if evidence_root else workspace / "knowledge-evidence"
        )
        catalog = YamlStandardCatalogReader().read(manifest)
        bindings = atlasdata_bindings(catalog, root=root)
        selected = set(document or ())
        for key in family or ():
            members = {name for name, binding in bindings.items() if binding.family_key == key}
            if not members:
                raise ValueError(f"family has no declared AtlasData physical documents: {key}")
            selected.update(members)
        if output is not None:
            output = (root / output).resolve()
            forbidden = [(workspace / "documents").resolve(), evidence_root]
            forbidden.extend(binding.source.parent for binding in bindings.values())
            if output == manifest or any(output.is_relative_to(path) for path in forbidden):
                raise ValueError(
                    "report must not overwrite manifests, public AtlasData, "
                    "canonical documents or evidence"
                )
        service = AtlasDataKnowledgeService(
            documents=FileSystemEngineeringDocumentRepository(workspace),
            bindings=bindings,
            evidence_root=evidence_root,
        )
        if set(selected) - bindings.keys():
            raise ValueError("selected keys must identify manifest-owned physical documents")
        missing = set()
        if available_only:
            requested = selected or set(bindings)
            available = {
                key
                for key in requested
                if (
                    service.documents.exists(DocumentKey(value=key))
                    if exporting
                    else bindings[key].enrichments_path.is_file()
                )
            }
            missing = requested - available
            selected = available
        if available_only and not selected:
            report = AtlasDataKnowledgeReport(
                operation="export" if exporting else "import",
                write_requested=write,
                document_keys=(),
                changed_targets=(),
                written_targets=(),
                status_counts={},
            )
        elif exporting:
            report = service.export(
                document_keys=tuple(sorted(selected)),
                write=write,
                dimensions=tuple(dimensions),
                clause_ids=tuple(clause_ids),
            )
        else:
            report = service.import_(
                document_keys=tuple(sorted(selected)), write=write, strict_evidence=strict_evidence
            )
        if missing:
            report = report.model_copy(
                update={
                    "status_counts": {
                        **report.status_counts,
                        "missing_document_or_companion": len(missing),
                    }
                }
            )
            for key in sorted(missing):
                typer.echo(f"Missing selected source  : {key}")
        if output is not None:
            atomic_write(output, (report.model_dump_json(indent=2) + "\n").encode(), private=True)
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Operation                : {report.operation}")
    typer.echo(f"Physical documents       : {len(report.document_keys)}")
    typer.echo(f"Changed targets          : {len(report.changed_targets)}")
    typer.echo(f"Written targets          : {len(report.written_targets)}")
    typer.echo(f"Content verified         : {report.content_verified_clauses}")
    typer.echo(f"Content not verifiable   : {report.content_unverified_clauses}")
    for status, count in report.status_counts.items():
        typer.echo(f"Attributes {status:<20}: {count}")
    for target in report.changed_targets:
        typer.echo(f"Target                   : {target}")
    if output:
        typer.echo(f"Change report            : {output}")
    if not write:
        typer.echo("Dry run only. Use --write to persist the selected knowledge.")
    typer.echo("No LLM calls. Structural AtlasData and its lifecycle status remain unchanged.")


@atlasdata_app.command("export-enrichments")
def export_enrichments(
    manifest: ManifestOption = Path("manifests/standards.yaml"),
    root: RootOption = Path("."),
    workspace: WorkspaceOption = Path(".atlas/data"),
    document: DocumentsOption = None,
    family: FamiliesOption = None,
    evidence_root: EvidenceOption = None,
    output: ReportOption = None,
    write: WriteOption = False,
    dimension: Annotated[
        list[str] | None,
        typer.Option(
            "--dimension",
            help="Repeat: statement_functions, knowledge_kinds, process_functions, "
            "applicability, role_semantics, subject_context, context_routing. Defaults to all.",
        ),
    ] = None,
    clause: Annotated[
        list[str] | None,
        typer.Option(
            "--clause",
            help="Clause ID; repeatable, requires one selected document.",
        ),
    ] = None,
    available_only: Annotated[
        bool, typer.Option("--available-only", help="Skip missing selected documents/companions.")
    ] = False,
) -> None:
    """Export selected canonical attributes beside their manifest-owned AtlasData sources."""
    _run(
        exporting=True,
        manifest=manifest,
        root=root,
        workspace=workspace,
        document=document,
        family=family,
        evidence_root=evidence_root,
        output=output,
        write=write,
        dimensions=dimension or (),
        clause_ids=clause or (),
        available_only=available_only,
    )


@atlasdata_app.command("import-enrichments")
def import_enrichments(
    manifest: ManifestOption = Path("manifests/standards.yaml"),
    root: RootOption = Path("."),
    workspace: WorkspaceOption = Path(".atlas/data"),
    document: DocumentsOption = None,
    family: FamiliesOption = None,
    evidence_root: EvidenceOption = None,
    output: ReportOption = None,
    write: WriteOption = False,
    strict_evidence: Annotated[
        bool,
        typer.Option(
            "--strict-evidence",
            help="Abort preflight when a referenced private value or raw evidence is missing.",
        ),
    ] = False,
    available_only: Annotated[
        bool, typer.Option("--available-only", help="Skip missing selected documents/companions.")
    ] = False,
) -> None:
    """Restore into existing documents or rebuild physical skeletons from AtlasData."""
    _run(
        exporting=False,
        manifest=manifest,
        root=root,
        workspace=workspace,
        document=document,
        family=family,
        evidence_root=evidence_root,
        output=output,
        write=write,
        strict_evidence=strict_evidence,
        available_only=available_only,
    )
