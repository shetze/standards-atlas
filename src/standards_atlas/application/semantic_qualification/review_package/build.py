"""Create real review work from existing source inputs; never synthesize gold labels."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.partial_comparison import (
    _output_is_separate,
)
from standards_atlas.application.semantic_qualification.partial_observations import PARTIAL_TASK
from standards_atlas.application.semantic_qualification.partial_proposals import (
    _json_bytes,
    load_partial_inputs,
)
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    QualificationCampaign,
    SemanticReferenceSuite,
)

from .model import ReviewPackage, ReviewProfile, SemanticPredicate, predicate_data
from .service import add_proposal, empty_state
from .sources import freeze_population, population_hash, select_holdout
from .storage import new_directory
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
) -> dict:
    spec = QualificationCampaign.load(manifest)
    if spec.review_bundle is not None:
        raise ValueError(
            "build review packages from the source campaign manifest, not a frozen handoff"
        )
    if output.exists():
        raise ValueError("review output exists; a rebuild never overwrites started reviews")
    profile = (
        ReviewProfile.model_validate(yaml.safe_load(profile_path.read_bytes()))
        if profile_path
        else ReviewProfile(attributes=spec.required_semantic_attributes)
    )
    if not set(spec.required_semantic_attributes) <= set(profile.attributes):
        raise ValueError("review profile cannot omit required campaign attributes")
    selection = load_partial_inputs(run=spec.run, dataset=spec.dataset)
    population = freeze_population(selection.examples)
    by_id = {s.example_id: s for s in population}
    by_coordinate = {(s.document_key, s.clause_id): s for s in population}
    known = set(development_ids)
    excluded, existing_holdout, suggestions = set(), set(), []
    input_paths = [spec.golden, *spec.semantic_suites, *spec.sentinel_suites, *development_suites]
    if profile_path:
        input_paths.append(profile_path)
    if instructions:
        input_paths.append(instructions)
    _output_is_separate(output.resolve(), tuple([manifest, spec.run or spec.dataset, *input_paths]))

    def bind_case(case):
        source = by_id.get(case["example_id"])
        if (
            source is None
            or source.document_key != case["document_key"]
            or (source.content_hash != case["content_hash"])
        ):
            raise ValueError(f"review reference missing or source drift: {case['example_id']}")
        if (
            "source_text" in case
            and normalized_content_hash(case["source_text"]) != source.content_hash
        ):
            raise ValueError("sentinel text does not match the frozen source")
        return source

    golden = ApplicabilityGoldenCorpus.load(spec.golden)
    for case in golden.cases:
        source = by_coordinate.get((case.document_key, case.clause_id))
        if case.status == "published" and (
            source is None or case.text.rstrip("\r\n") != source.text.rstrip("\r\n")
        ):
            raise ValueError(f"published Golden source missing or changed: {case.clause_id}")
        if source is not None:
            excluded.add(source.example_id)  # Also exclude known draft/previously reviewed cases.
    seen_suites = set()
    for path in (*spec.semantic_suites, *development_suites):
        suite = SemanticReferenceSuite.model_validate(yaml.safe_load(path.read_bytes()))
        if path in development_suites and suite.split != "development":
            raise ValueError("--development-suite requires a Development suite")
        if suite.id in seen_suites:
            raise ValueError("duplicate existing semantic suite identity")
        seen_suites.add(suite.id)
        # New-format prior reviews must retain their context binding too.
        if (suite.review_reference or "").startswith("atlas-review:"):
            from .publication import load_bound_suite

            load_bound_suite(path, selection.examples)
        for case in suite.cases:
            bind_case(case.model_dump())
            if set(case.attributes) - set(profile.attributes):
                raise ValueError("review profile must retain all existing suite attributes")
            (known if suite.split == "development" else existing_holdout).add(case.example_id)
            for attribute, predicate in case.attributes.items():
                suggestions.append(
                    dict(
                        example_id=case.example_id,
                        attribute=attribute,
                        predicate=SemanticPredicate.model_validate(predicate_data(predicate)),
                        producer=suite.reviewed_by or suite.id,
                        producer_kind="historical",
                        rationale=(
                            "Existing reference; reconfirm against frozen text/context/rules."
                        ),
                        provenance=f"{path}: {suite.id}@{suite.version}; {suite.status}; "
                        f"review_reference={suite.review_reference}",
                    )
                )
    for path in spec.sentinel_suites:
        suite = json.loads(path.read_bytes())
        require_supported_schema("semantic-readiness-checks", suite.get("schema_version"))
        if suite.get("kind") != "semantic-readiness-checks" or not suite.get("cases"):
            raise ValueError("invalid sentinel suite")
        ids = [case["example_id"] for case in suite["cases"]]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate sentinel identity")
        for case in suite["cases"]:
            source = bind_case(case)
            known.add(source.example_id)
            if "process_check" in case:
                suggestions.append(
                    dict(
                        example_id=source.example_id,
                        attribute="process_functions",
                        predicate=SemanticPredicate.model_validate(case["process_check"]),
                        producer=suite.get("id", "engineering-sentinel"),
                        producer_kind="engineering",
                        rationale=(
                            case.get("review_basis")
                            or "Engineering sentinel, not confirmed HITL gold."
                        ),
                        provenance=str(path),
                    )
                )
    if not known or not known <= by_id.keys():
        raise ValueError("need known Development cases from suites, sentinels or --development-id")
    excluded |= known
    holdout = select_holdout(
        population, excluded, existing_holdout, holdout_size, spec.seed if seed is None else seed
    )
    # The canonical observation contract plus stable reference guidance, not candidate outputs.
    rule_paths = [
        resources / "tasks" / PARTIAL_TASK / "1.0.0" / name for name in ("schema.json", "task.yaml")
    ]
    rule_paths += [
        resources / "profiles/functional-safety/1.0.0/profile.yaml",
        resources / "review/partial-semantic-reference-v1/guidelines.md",
    ]
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
                    "attributes": profile.attributes,
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
            "seed": spec.seed if seed is None else seed,
            "source_location": {
                "run" if spec.run else "dataset": str((spec.run or spec.dataset).resolve()),
            },
            "campaign_manifest": {
                "path": str(manifest.resolve()),
                "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            },
            "input_files": {
                str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in input_paths
            },
            "rules": rules,
            "rules_sha256": structure_fingerprint(rules),
            "output_schema": json.loads(rules[f"tasks/{PARTIAL_TASK}/1.0.0/schema.json"]),
        },
        "package_sha256",
    )
    verify_package(package)
    state = empty_state(package)
    for suggestion in suggestions:
        state = add_proposal(package, state, **suggestion, created_at=now)
    report = review_report(package, state)
    readme = (
        "# Partial semantic review package\n\n"
        "Source text and structural facts are immutable. Legacy context remains unattributed.\n"
        "No inherited suggestion is a newly confirmed human decision.\n"
        "Use `evaluation partial-review-show` and `partial-review-decide`; "
        "do not edit hashes/JSON.\n"
        "Use `partial-review-import --dry-run` to check current source binding and coverage.\n"
        "Publication needs every selected attribute decided "
        "and an explicit holdout-use declaration.\n"
        "See docs/user-guide/partial-review-packages.md. "
        "Web/MCP review adapters follow separately.\n"
    )
    new_directory(
        output,
        {
            "review-package.json": _json_bytes(package.model_dump(mode="json")),
            "review-state.json": _json_bytes(state.model_dump(mode="json")),
            "README.md": readme.encode("utf-8"),
        },
    )
    return report
