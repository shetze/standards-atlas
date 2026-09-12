"""Build a separate source-readiness pilot without qualifying rules or editing sources."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from standards_atlas.application.context.source_structure import project_source_structure
from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.partial_diagnostics import (
    describe_partial_plan,
    summarize_partial_plans,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    PartialInputSelection,
    load_partial_inputs,
)
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialProposalConfig,
    PartialTaskResources,
    prepare_partial_request,
)
from standards_atlas.domain.model import Clause, ClauseId, ClauseType, StandardReference, TextBlock

SUITE_PATH = "qualification/taxonomy-readiness-v1/cases.yaml"


def synthetic_pilot(resources: Path, *, dataset_version: str) -> tuple[PartialInputSelection, dict]:
    """Construct explicit test-only authority; never attach it to real standards."""
    definition = yaml.safe_load((resources / SUITE_PATH).read_text(encoding="utf-8"))
    require_supported_schema("taxonomy-readiness-cases", definition.get("schema_version"))
    examples, expectations = [], []
    for number, case in enumerate(definition["cases"], 1):
        identity = "pilot-" + case["id"]
        reference, text = str(number), case["text"]
        clause = Clause(
            id=ClauseId(value=identity),
            reference=StandardReference(standard="ATLAS-PILOT", clause=reference),
            clause_type=ClauseType(case["clause_type"]),
            heading=case["heading"],
            content=(TextBlock(id="text", text=text),),
        )
        if case.get("confirm_fields"):
            clause = clause.confirm_authoritative(
                *case["confirm_fields"],
                authority="fixture:taxonomy-readiness-v1",
            )
        parents = ()
        if case.get("parent_heading"):
            parents = (
                Clause(
                    id=ClauseId(value=identity + "-parent"),
                    reference=StandardReference(
                        standard="ATLAS-PILOT", clause=reference + ".parent"
                    ),
                    clause_type=ClauseType.TOC,
                    heading=case["parent_heading"],
                ),
            )
        digest = normalized_content_hash(text)
        structure = project_source_structure(
            clause,
            document_key="ATLAS-PILOT",
            content_hash=digest,
            ancestors=parents,
        )
        context = {
            "document_key": "ATLAS-PILOT",
            "clause_id": identity,
            "reference": reference,
            "knowledge_domain": "functional-safety",
            "heading": case["heading"],
            "clause_type": case["clause_type"],
            "source_structure": structure.model_dump(mode="json"),
        }
        examples.append(
            EvaluationExample(
                id=identity,
                input={"context": context, "content": {"text": text, "hash": digest}},
                expected={},
            )
        )
        expectations.append(
            {
                "example_id": identity,
                "document_key": "ATLAS-PILOT",
                "content_hash": digest,
                **{
                    k: case[k]
                    for k in ("expected_primary_state", "expected_primary_value", "process_check")
                    if k in case
                },
            }
        )
    suite = {
        "schema_version": "1.0",
        "kind": "semantic-readiness-checks",
        "id": definition["id"],
        "version": definition["version"],
        "qualification_status": "synthetic-smoke-not-domain-gold",
        "cases": expectations,
    }
    return PartialInputSelection(tuple(examples), {}, "source-dataset", dataset_version), suite


def build_taxonomy_pilot(
    *,
    output_directory: Path,
    resources: Path,
    run: Path | None = None,
    dataset: Path | None = None,
    synthetic_smoke: bool = False,
    dataset_version: str = "2.2.0",
    limit: int = 24,
) -> dict[str, Any]:
    """Select actual fixed/hint/conflict/open sources and export a source-bound review.

    A legacy corpus can produce a useful review pilot with zero fixed attributes;
    the output explicitly reports that it cannot demonstrate taxonomy savings.
    """
    if limit < 1:
        raise ValueError("pilot limit must be positive")
    if synthetic_smoke and (run is not None or dataset is not None):
        raise ValueError("synthetic smoke cannot be mixed with real source inputs")
    output = output_directory.resolve()
    if output.exists():
        raise ValueError("pilot output must be a new directory")
    for path in (run, dataset):
        if path is not None and (
            output == path.resolve() or (path.is_dir() and output.is_relative_to(path.resolve()))
        ):
            raise ValueError("pilot must be separate from its source")
    for protected in (
        "data",
        "src/standards_atlas/resources",
        ".atlas/data/documents",
        ".atlas/data/knowledge-evidence",
    ):
        if output.is_relative_to(Path(protected).resolve()):
            raise ValueError("pilot must be separate from canonical/public data")
    if synthetic_smoke:
        source, checks = synthetic_pilot(resources, dataset_version=dataset_version)
    else:
        source, checks = load_partial_inputs(run=run, dataset=dataset), None
    if not source.examples or len({e.id for e in source.examples}) != len(source.examples):
        raise ValueError("pilot source must have unique nonempty example identities")
    config = PartialProposalConfig(
        corpus_id=source.corpus_id,
        dataset_version=source.dataset_version,
        provider="planning-only",
        model="none",
        prompt_version="taxonomy-partial-v2",
    )
    task = PartialTaskResources.load(resources, config)
    groups = defaultdict(deque)
    by_id = {}
    for example in source.examples:
        prepared = prepare_partial_request(config, example.id, example.input, task)
        plan = prepared.plan
        states = {d.state for d in plan.decision_plan.decisions}
        bucket = (
            "fixed"
            if plan.fixed_attributes
            else ("conflict" if "conflict" in states else "hint" if "hint" in states else "open")
        )
        groups[bucket].append(example)
        by_id[example.id] = plan
    # Round-robin avoids a fixed-only sample hiding all known structural boundary cases.
    selected = []
    while len(selected) < limit and any(groups.values()):
        for bucket in ("fixed", "conflict", "hint", "open"):
            if groups[bucket] and len(selected) < limit:
                selected.append(groups[bucket].popleft())
    plans = [by_id[e.id] for e in selected]
    descriptions = [describe_partial_plan(p) for p in plans]
    if checks:
        ids = {e.id for e in selected}
        checks["cases"] = [c for c in checks["cases"] if c["example_id"] in ids]
    report = {
        "schema_version": "1.0",
        "kind": "taxonomy-pilot-readiness",
        "scope": "synthetic-smoke" if synthetic_smoke else "source-bound-review",
        "input_count": len(source.examples),
        "selected_count": len(selected),
        "source_fingerprints": source.fingerprints,
        "ready_to_test_fixed_attributes": any(p.fixed_attributes for p in plans),
        "new_rule_qualifications": [],
        "source_authority_modified": False,
        "fixture_authority_constructed": synthetic_smoke,
        "model_calls": 0,
        "production_benchmark": False,
        "selection_policy": "fixed/conflict/hint/open round-robin; not representative",
        "decision_plan_summary": summarize_partial_plans(plans),
        "cases": [
            {"example_id": e.id, "clause": p.clause.model_dump(mode="json"), "plan": d}
            for e, p, d in zip(selected, plans, descriptions, strict=True)
        ],
    }
    output.mkdir(parents=True)
    (output / "dataset.json").write_text(
        json.dumps(
            {
                "task": "semantic-attribute-observation",
                "version": source.dataset_version,
                "corpus_id": source.corpus_id,
                "examples": [asdict(e) | {"expected": {}, "tags": []} for e in selected],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "pilot-readiness.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if checks:
        (output / "readiness-checks.json").write_text(
            json.dumps(checks, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    fields = [
        "example_id",
        "document_key",
        "reference",
        "content_hash",
        "attribute",
        "state",
        "candidates",
        "rule_ids",
        "source_sha256",
        "rules_sha256",
        "review_status",
        "reviewer",
        "rationale",
        "text",
        "source_facts",
    ]
    with (output / "source-review.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for example, plan in zip(selected, plans, strict=True):
            for decision in plan.decision_plan.decisions:
                if decision.state == "open":
                    continue
                writer.writerow(
                    {
                        "example_id": example.id,
                        "document_key": plan.clause.document_key,
                        "reference": plan.decision_plan.source.reference,
                        "content_hash": plan.clause.content_hash,
                        "attribute": decision.attribute,
                        "state": decision.state,
                        "candidates": json.dumps(decision.candidates),
                        "rule_ids": ",".join(sorted({e.rule_id for e in decision.evidence})),
                        "source_sha256": plan.decision_plan.source_sha256,
                        "rules_sha256": plan.decision_plan.rules_sha256,
                        "review_status": "pending",
                        "reviewer": "",
                        "rationale": "",
                        "text": example.input["content"]["text"],
                        "source_facts": json.dumps(
                            plan.decision_plan.source.model_dump(mode="json")
                        ),
                    }
                )
    status_counts = Counter(p.decision_plan.decision("primary_function").state for p in plans)
    (output / "README.md").write_text(
        "# Taxonomy readiness pilot\n\n"
        f"Scope: **{report['scope']}**; {len(selected)} selected clauses.\n\n"
        f"Primary plan states: {dict(status_counts)}.\n\n"
        "Source facts and rule qualification are independent gates. No pending rule was promoted. "
        "No real source was retrospectively confirmed. The synthetic option constructs only "
        "explicit fixture authority, never independent human review.\n\n"
        "Use dataset.json for partial-proposals or partial-cascade; expectations are separate. "
        "Use --require-taxonomy-decisions before an intended taxonomy-saving cascade run. "
        "Fill source-review.csv for fachlicher review; it is not an automatic import/approval. "
        "Confirmed real facts must come through the canonical source workflow.\n\n"
        "This deliberately stratified pilot and its smoke results are not the "
        "80% corpus benchmark.\n",
        encoding="utf-8",
    )
    return report
