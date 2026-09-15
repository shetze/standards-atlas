"""Create source-bound applicability-presence review packages."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.clause_access import ClauseProvider

from .model import (
    ReviewPackage,
    ReviewPredicate,
    ReviewProfile,
    ReviewReferenceSuite,
    ReviewSourceSpec,
)
from .service import add_proposal, empty_state
from .sources import (
    canonical_enrichment_suggestions,
    freeze_population,
    load_review_inputs,
    population_hash,
    select_holdout,
)
from .storage import _json_bytes, new_directory, output_is_separate
from .validation import review_report, seal, verify_package


def build_review_package(
    *,
    manifest: Path,
    output: Path,
    resources: Path,
    holdout_size: int = 20,
    seed: int | None = None,
    review_id: str | None = None,
    version: str = "1.0.0",
    development_ids: tuple[str, ...] = (),
    development_suites: tuple[Path, ...] = (),
    profile_path: Path | None = None,
    instructions: Path | None = None,
    clause_provider: ClauseProvider | None = None,
) -> dict:
    spec = ReviewSourceSpec.load(manifest)
    if output.exists():
        raise ValueError("review output exists; a rebuild never overwrites started reviews")
    profile = (
        ReviewProfile.model_validate(yaml.safe_load(profile_path.read_bytes()))
        if profile_path
        else ReviewProfile()
    )
    selection = load_review_inputs(run=spec.run, dataset=spec.dataset)
    population = freeze_population(selection.examples)
    by_id = {s.example_id: s for s in population}
    by_coordinate = {(s.document_key, s.clause_id): s for s in population}
    known = set(development_ids)
    excluded, existing_holdout, suggestions = set(), set(), []
    input_paths = [spec.golden, *spec.reference_suites, *development_suites]
    if profile_path:
        input_paths.append(profile_path)
    if instructions:
        input_paths.append(instructions)
    output_is_separate(output.resolve(), tuple([manifest, spec.run or spec.dataset, *input_paths]))

    golden = ApplicabilityGoldenCorpus.load(spec.golden)
    for case in golden.cases:
        source = by_coordinate.get((case.document_key, case.clause_id))
        if source is None:
            continue
        if case.text.rstrip("\r\n") != source.text.rstrip("\r\n"):
            raise ValueError(f"Golden source changed: {case.clause_id}")
        excluded.add(source.example_id)
        if case.status == "published" and case.expected is not None:
            known.add(source.example_id)
            suggestions.append(
                dict(
                    example_id=source.example_id,
                    attribute="applicability_present",
                    predicate=ReviewPredicate(equals=case.expected.present),
                    producer=golden.corpus_id,
                    producer_kind="historical",
                    rationale="Existing published applicability reference; reconfirm against frozen source.",
                    provenance=f"{spec.golden}: {golden.corpus_id}@{golden.corpus_version}",
                )
            )

    for path in (*spec.reference_suites, *development_suites):
        suite = ReviewReferenceSuite.model_validate(yaml.safe_load(path.read_bytes()))
        if path in development_suites and suite.split != "development":
            raise ValueError("--development-suite requires a Development suite")
        for case in suite.cases:
            source = by_id.get(case.example_id)
            if (
                source is None
                or source.document_key != case.document_key
                or source.content_hash != case.content_hash
            ):
                raise ValueError(f"review reference missing or source drift: {case.example_id}")
            (known if suite.split == "development" else existing_holdout).add(case.example_id)
            excluded.add(case.example_id)
            predicate = case.attributes["applicability_present"]
            suggestions.append(
                dict(
                    example_id=case.example_id,
                    attribute="applicability_present",
                    predicate=predicate,
                    producer=suite.reviewed_by or suite.id,
                    producer_kind="historical",
                    rationale="Existing review reference; reconfirm against frozen source.",
                    provenance=f"{path}: {suite.id}@{suite.version}; {suite.status}",
                )
            )

    if not known or not known <= by_id.keys():
        raise ValueError("review needs at least one known Development case")
    excluded |= known
    actual_seed = spec.seed if seed is None else seed
    holdout = select_holdout(population, excluded, existing_holdout, holdout_size, actual_seed)

    rule_paths = [
        resources / "tasks/applicability-presence/1.0.0" / name
        for name in ("schema.json", "task.yaml")
    ]
    rule_paths.append(resources / "review/applicability-presence-v1/guidelines.md")
    rules = {str(p.relative_to(resources)): p.read_text(encoding="utf-8") for p in rule_paths}
    if instructions:
        rules["project-review-instructions"] = instructions.read_text(encoding="utf-8")
    input_paths += rule_paths
    now = datetime.now(UTC)
    package = seal(
        ReviewPackage,
        {
            "id": review_id or f"{spec.id}-review",
            "version": version,
            "created_at": now,
            "profile": profile.model_dump(mode="json"),
            "population": [s.model_dump(mode="json") for s in population],
            "population_sha256": population_hash(population),
            "cases": [
                {
                    "example_id": i,
                    "split": split,
                    "attributes": ["applicability_present"],
                    "selection_reasons": [
                        "known-development"
                        if split == "development"
                        else "source-only-disjoint-holdout"
                    ],
                }
                for split, ids in (("development", sorted(known)), ("holdout", holdout))
                for i in ids
            ],
            "known_development_ids": sorted(known),
            "excluded_holdout_ids": sorted(excluded),
            "existing_holdout_ids": sorted(existing_holdout),
            "holdout_size": holdout_size,
            "seed": actual_seed,
            "source_location": {
                "run" if spec.run else "dataset": str((spec.run or spec.dataset).resolve())
            },
            "source_manifest": {
                "path": str(manifest.resolve()),
                "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            },
            "input_files": {
                str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in input_paths
            },
            "rules": rules,
            "rules_sha256": structure_fingerprint(rules),
            "output_schema": json.loads(rules["tasks/applicability-presence/1.0.0/schema.json"]),
        },
        "package_sha256",
    )
    verify_package(package)
    if clause_provider is not None:
        suggestions.extend(canonical_enrichment_suggestions(package, clause_provider))
    state = empty_state(package)
    for suggestion in suggestions:
        state = add_proposal(package, state, **suggestion, created_at=now)
    report = review_report(package, state)
    readme = "# Applicability review package\n\nFrozen source/context and applicability-presence review. Proposals are not human decisions.\n"
    new_directory(
        output,
        {
            "review-package.json": _json_bytes(package.model_dump(mode="json")),
            "review-state.json": _json_bytes(state.model_dump(mode="json")),
            "README.md": readme.encode(),
        },
    )
    return report
