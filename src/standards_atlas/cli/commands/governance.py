"""Governance selection profile commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.application.governance import (
    GovernanceSelectionProfileError,
    load_governance_selection_profile,
    render_governance_selection_profile,
)
from standards_atlas.cli.apps import governance_profile_app


@governance_profile_app.command("validate")
def validate_governance_profile(
    profile: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Selection profile YAML."),
    ],
) -> None:
    """Validate a governance selection profile."""
    try:
        loaded = load_governance_selection_profile(profile)
    except GovernanceSelectionProfileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Governance profile : {loaded.id}")
    typer.echo(f"Version            : {loaded.version}")
    typer.echo(f"Domain             : {loaded.context.domain}")
    typer.echo("Profile is valid")


@governance_profile_app.command("show")
def show_governance_profile(
    profile: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Selection profile YAML."),
    ],
) -> None:
    """Render the canonical normalized governance selection profile."""
    try:
        loaded = load_governance_selection_profile(profile)
    except GovernanceSelectionProfileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(render_governance_selection_profile(loaded), nl=False)


@governance_profile_app.command("select")
def select_governance_candidates(
    profile: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Selection profile YAML."),
    ],
    document: Annotated[
        list[str] | None,
        typer.Option(
            "--document",
            help=(
                "Persisted document key to analyze; repeat as needed. "
                "Defaults to profile standards.include."
            ),
        ),
    ] = None,
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            "-w",
            help="Standards Atlas workspace directory.",
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path(".atlas/data"),
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Candidate analysis JSON. Defaults to "
                "local/review/governance/<profile-id>/candidate-analysis.json."
            ),
            file_okay=True,
            dir_okay=False,
        ),
    ] = None,
    replace_existing: Annotated[
        bool,
        typer.Option("--replace/--no-replace", help="Replace existing analysis artifacts."),
    ] = True,
) -> None:
    """Analyze Gemara control candidates against a governance selection profile."""
    from standards_atlas.adapters.filesystem import (
        FileSystemEngineeringDocumentRepository,
        FileSystemPublicationDocumentProvider,
    )
    from standards_atlas.adapters.governance import (
        GovernanceCandidateAnalyzer,
        write_candidate_analysis,
    )

    try:
        loaded_profile = load_governance_selection_profile(profile)
    except GovernanceSelectionProfileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    document_keys = tuple(document or loaded_profile.standards.include)
    if not document_keys:
        typer.echo(
            "No documents selected; provide --document or standards.include in the profile.",
            err=True,
        )
        raise typer.Exit(code=2)

    repository = FileSystemEngineeringDocumentRepository(workspace=workspace)
    publications = FileSystemPublicationDocumentProvider(repository)
    try:
        documents = tuple(publications.load(key) for key in document_keys)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    analysis = GovernanceCandidateAnalyzer().analyze(loaded_profile, documents)
    target = output or (
        Path("local/review/governance") / loaded_profile.id / "candidate-analysis.json"
    )
    try:
        json_path, csv_path = write_candidate_analysis(
            analysis,
            target,
            replace_existing=replace_existing,
        )
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc

    typer.echo(f"Governance profile : {loaded_profile.id}")
    typer.echo(f"Documents          : {len(documents)}")
    typer.echo(f"Candidates         : {len(analysis.candidates)}")
    typer.echo(f"Selected           : {analysis.selected}")
    typer.echo(f"Excluded           : {analysis.excluded}")
    typer.echo(f"Undetermined       : {analysis.undetermined}")
    typer.echo(f"Analysis JSON      : {json_path}")
    typer.echo(f"Review CSV         : {csv_path}")


@governance_profile_app.command("export-policy")
def export_governance_policy_scaffold(
    profile: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Selection profile YAML."),
    ],
    responsible: Annotated[
        list[str] | None,
        typer.Option(
            "--responsible",
            help="Responsible policy contact name; repeat as needed.",
        ),
    ] = None,
    accountable: Annotated[
        list[str] | None,
        typer.Option(
            "--accountable",
            help="Accountable policy contact name; repeat as needed.",
        ),
    ] = None,
    document: Annotated[
        list[str] | None,
        typer.Option(
            "--document",
            help=(
                "Persisted document key to include; repeat as needed. "
                "Defaults to profile standards.include."
            ),
        ),
    ] = None,
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            "-w",
            help="Standards Atlas workspace directory.",
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path(".atlas/data"),
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Gemara Policy scaffold YAML. Defaults to "
                "local/exports/governance/<profile-id>/policy.yaml."
            ),
            file_okay=True,
            dir_okay=False,
        ),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option("--title", help="Optional human-readable policy title."),
    ] = None,
    withhold_undetermined: Annotated[
        bool,
        typer.Option(
            "--withhold-undetermined/--reject-undetermined",
            help=(
                "Create a draft while excluding undetermined controls. "
                "By default undetermined candidates block policy export."
            ),
        ),
    ] = False,
    replace_existing: Annotated[
        bool,
        typer.Option("--replace/--no-replace", help="Replace existing policy artifacts."),
    ] = True,
) -> None:
    """Export a draft Gemara Policy scaffold from deterministic candidate analysis."""
    from standards_atlas.adapters.filesystem import (
        FileSystemEngineeringDocumentRepository,
        FileSystemPublicationDocumentProvider,
    )
    from standards_atlas.adapters.governance import (
        GovernanceCandidateAnalyzer,
        GovernancePolicyScaffoldExporter,
    )

    try:
        loaded_profile = load_governance_selection_profile(profile)
    except GovernanceSelectionProfileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if not responsible or not accountable:
        typer.echo(
            "Gemara Policy scaffold requires --responsible and --accountable.",
            err=True,
        )
        raise typer.Exit(code=2)

    document_keys = tuple(document or loaded_profile.standards.include)
    if not document_keys:
        typer.echo(
            "No documents selected; provide --document or standards.include in the profile.",
            err=True,
        )
        raise typer.Exit(code=2)

    repository = FileSystemEngineeringDocumentRepository(workspace=workspace)
    publications = FileSystemPublicationDocumentProvider(repository)
    try:
        documents = tuple(publications.load(key) for key in document_keys)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    analysis = GovernanceCandidateAnalyzer().analyze(loaded_profile, documents)
    target = output or (Path("local/exports/governance") / loaded_profile.id / "policy.yaml")
    try:
        policy_path, manifest_path = GovernancePolicyScaffoldExporter().export(
            loaded_profile,
            analysis,
            documents,
            target,
            responsible=tuple(responsible),
            accountable=tuple(accountable),
            title=title,
            withhold_undetermined=withhold_undetermined,
            replace_existing=replace_existing,
        )
    except (ValueError, FileExistsError) as exc:
        typer.echo(f"Governance policy export failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    typer.echo(f"Governance profile : {loaded_profile.id}")
    typer.echo(f"Documents          : {len(documents)}")
    typer.echo(f"Selected           : {analysis.selected}")
    typer.echo(f"Excluded           : {analysis.excluded}")
    typer.echo(f"Undetermined       : {analysis.undetermined}")
    typer.echo(f"Policy scaffold    : {policy_path}")
    typer.echo(f"Scaffold manifest  : {manifest_path}")
