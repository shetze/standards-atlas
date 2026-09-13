"""Local human adapter for review preparation; no implicit approvals or model startup."""

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import typer
import yaml

from standards_atlas.application.semantic_qualification.review_package.build import (
    build_review_package,
)
from standards_atlas.application.semantic_qualification.review_package.model import (
    SemanticPredicate,
)
from standards_atlas.application.semantic_qualification.review_package.publication import (
    import_review_package,
)
from standards_atlas.application.semantic_qualification.review_package.service import (
    describe_review,
    record_decision,
)
from standards_atlas.cli import defaults
from standards_atlas.cli.apps import evaluation_app


@contextmanager
def _errors():
    try:
        yield
    except (OSError, ValueError, KeyError, TypeError, BadZipFile, yaml.YAMLError) as exc:
        typer.echo(f"Partial review failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _show(value: dict) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))


@evaluation_app.command("partial-review-build")
def build_partial_review_command(
    manifest: Annotated[Path, typer.Option("--manifest", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", file_okay=False)],
    holdout_size: Annotated[int, typer.Option("--holdout-size", min=1)] = 20,
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    review_id: Annotated[str | None, typer.Option("--id")] = None,
    version: Annotated[str, typer.Option("--version")] = "1.0.0",
    development_id: Annotated[list[str] | None, typer.Option("--development-id")] = None,
    development_suite: Annotated[
        list[Path] | None, typer.Option("--development-suite", exists=True, dir_okay=False)
    ] = None,
    profile: Annotated[Path | None, typer.Option("--profile", exists=True, dir_okay=False)] = None,
    instructions: Annotated[
        Path | None, typer.Option("--instructions", exists=True, dir_okay=False)
    ] = None,
    resources: Annotated[Path, typer.Option("--resources", file_okay=False)] = (
        defaults.DEFAULT_EVALUATION_RESOURCES
    ),
) -> None:
    """Freeze Development, source-only disjoint holdout, original text, context and rules."""
    with _errors():
        result = build_review_package(
            manifest=manifest,
            output=output,
            resources=resources,
            holdout_size=holdout_size,
            seed=seed,
            review_id=review_id,
            version=version,
            development_ids=tuple(development_id or ()),
            development_suites=tuple(development_suite or ()),
            profile_path=profile,
            instructions=instructions,
        )
    _show(result)


@evaluation_app.command("partial-review-show")
def show_partial_review_command(
    package: Annotated[Path, typer.Option("--package", exists=True, file_okay=False)],
    case: Annotated[str | None, typer.Option("--case")] = None,
) -> None:
    """Show coverage or a complete case, with separate suggestions and human reviews."""
    with _errors():
        result = describe_review(package, example_id=case)
    _show(result)


@evaluation_app.command("partial-review-decide")
def decide_partial_review_command(
    package: Annotated[Path, typer.Option("--package", exists=True, file_okay=False)],
    case: Annotated[str, typer.Option("--case")],
    attribute: Annotated[str, typer.Option("--attribute")],
    status: Annotated[
        str, typer.Option("--status", help="confirmed, corrected, deferred, rejected")
    ],
    reviewer: Annotated[str, typer.Option("--reviewer")],
    revision: Annotated[int, typer.Option("--revision", min=0)],
    proposal: Annotated[str | None, typer.Option("--proposal")] = None,
    equals: Annotated[
        str | None, typer.Option("--equals", help='JSON value, e.g. false, null, ["activity"]')
    ] = None,
    must_include: Annotated[list[str] | None, typer.Option("--must-include")] = None,
    must_be_empty: Annotated[bool, typer.Option("--must-be-empty")] = False,
    comment: Annotated[str, typer.Option("--comment")] = "",
) -> None:
    """Record one explicit human attribute decision; use the revision shown by the last read."""
    with _errors():
        if sum((equals is not None, bool(must_include), must_be_empty)) > 1:
            raise ValueError("choose at most one explicit predicate operator")
        predicate = None
        if equals is not None:
            predicate = SemanticPredicate(equals=json.loads(equals))
        elif must_include:
            predicate = SemanticPredicate(must_include=tuple(must_include))
        elif must_be_empty:
            predicate = SemanticPredicate(must_be_empty=True)
        state = record_decision(
            package,
            expected_revision=revision,
            example_id=case,
            attribute=attribute,
            status=status,
            reviewer=reviewer,
            proposal_sha256=proposal,
            predicate=predicate,
            comment=comment,
        )
    _show(
        {
            "revision": state.revision,
            "state_sha256": state.state_sha256,
            "decision": state.decisions[-1].model_dump(mode="json"),
        }
    )


@evaluation_app.command("partial-review-import")
def import_partial_review_command(
    package: Annotated[Path, typer.Option("--package", exists=True, file_okay=False)],
    output: Annotated[Path | None, typer.Option("--output", file_okay=False)] = None,
    publish: Annotated[bool, typer.Option("--publish")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    holdout_declaration: Annotated[str | None, typer.Option("--holdout-declaration")] = None,
    run: Annotated[Path | None, typer.Option("--run", exists=True)] = None,
    dataset: Annotated[Path | None, typer.Option("--dataset", exists=True, dir_okay=False)] = None,
) -> None:
    """Validate live sources; atomically write both suites and evidence, draft unless --publish."""
    with _errors():
        result = import_review_package(
            package=package,
            output=output,
            publish=publish,
            dry_run=dry_run,
            holdout_declaration=holdout_declaration,
            run=run,
            dataset=dataset,
        )
    _show(result)
    if not result["importable"]:
        raise typer.Exit(code=1)
