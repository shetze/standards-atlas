"""Model-free, read-only reporting of taxonomy decision plans."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
from collections import Counter, defaultdict
from importlib.resources import files
from pathlib import Path
from typing import Any

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.semantic_qualification.cascade_replay_source import (
    CascadeReplaySource,
)
from standards_atlas.application.semantic_qualification.structural_evidence import (
    derive_structural_evidence,
    taxonomy_structural_evidence,
)
from standards_atlas.application.semantic_qualification.taxonomy_decisions import (
    DECISION_ATTRIBUTES,
    RESOURCE_DIRECTORY,
    ClauseDecisionPlan,
    derive_clause_decision_plan,
    load_taxonomy_rules,
)


def diagnose_taxonomy_decisions(
    *,
    output_directory: Path,
    run: Path | None = None,
    dataset: Path | None = None,
) -> tuple[Path, Path]:
    """Write a separate diagnostic; never update a run, model cache or canonical data.

    A run is verified using its immutable selection and archived checksums. A
    standalone dataset is useful for newly built, source-attributed CBoxes.
    Expected labels and tags are never passed to the rule engine.
    """
    if (run is None) == (dataset is None):
        raise ValueError("provide exactly one of --run or --dataset")
    source_path = (run or dataset).resolve()
    destination = output_directory.resolve()
    if destination.exists():
        raise ValueError("taxonomy output must be a new, separate directory")
    if source_path.is_dir() and destination.is_relative_to(source_path):
        raise ValueError("taxonomy output must be outside the source run directory")
    if destination == source_path:
        raise ValueError("taxonomy output must not replace the input")

    fingerprints: dict[str, str] = {}
    if run is not None:
        source = CascadeReplaySource(run)
        try:
            selection = source.selection()
            with tempfile.TemporaryDirectory(prefix="atlas-taxonomy-input-") as temporary:
                examples = source.materialize_inputs(selection, Path(temporary))
            fingerprints.update(source.fingerprints)
        finally:
            source.close()
    else:
        raw = dataset.read_bytes()
        fingerprints[str(dataset.resolve())] = hashlib.sha256(raw).hexdigest()
        payload = json.loads(raw)
        examples = tuple(
            EvaluationExample(id=item["id"], input=item["input"], expected={})
            for item in payload["examples"]
        )
    if not examples:
        raise ValueError("taxonomy diagnostics require a nonempty selected dataset")

    plans: list[ClauseDecisionPlan] = []
    comparisons = []
    coordinates = set()
    example_ids = set()
    clause_ids = set()
    for example in examples:
        if example.id in example_ids:
            raise ValueError("duplicate example identity in taxonomy dataset")
        example_ids.add(example.id)
        context, content = example.input["context"], example.input["content"]
        coordinate = (context.get("document_key"), context.get("clause_id"))
        if coordinate in coordinates:
            raise ValueError("duplicate clause identity in taxonomy dataset")
        coordinates.add(coordinate)
        if coordinate[1] in clause_ids:
            raise ValueError("duplicate clause id in taxonomy dataset")
        clause_ids.add(coordinate[1])
        plan = derive_clause_decision_plan(
            context,
            text=content["text"],
            content_hash=content.get("hash"),
        )
        plans.append(plan)
        prior = derive_structural_evidence(
            {**context, "text": content["text"]},
            policy="legacy-v1",
        ).as_dict()
        primary = plan.decision("primary_function")
        projected = taxonomy_structural_evidence(plan)["attributes"]["primary_function"]
        old = prior.get("primary_function")
        comparisons.append(
            {
                "clause_id": plan.source.clause_id,
                "document_key": plan.source.document_key,
                "reference": plan.source.reference,
                "legacy_primary": old,
                "diagnostic_primary_state": projected["state"],
                "diagnostic_primary": projected["value"],
                "diagnostic_candidates": list(primary.candidates),
                "fixed_primary_would_change": primary.state == "fixed" and primary.value != old,
                "legacy_primary_not_fixed_by_plan": old is not None and primary.value != old,
            }
        )

    summary = summarize_plans(plans)
    summary["comparison"] = {
        "fixed_primary_would_change": sum(
            item["fixed_primary_would_change"] for item in comparisons
        ),
        "legacy_primary_not_fixed_by_plan": sum(
            item["legacy_primary_not_fixed_by_plan"] for item in comparisons
        ),
    }
    profile = load_taxonomy_rules()
    report = {
        "schema_version": "1.0",
        "diagnostic_only": True,
        "model_inference_performed": False,
        "production_routing_changed": False,
        "canonical_adoption_performed": False,
        "source": str(source_path),
        "input_fingerprints": fingerprints,
        "rules_id": profile.id,
        "rules_version": profile.version,
        "rules_sha256": profile.fingerprint,
        "plan_fingerprints": {plan.source.clause_id: plan.fingerprint for plan in plans},
        "summary": summary,
        "comparisons": comparisons,
        "limitations": [
            "Diagnostic fixed attributes are not active acceptance decisions or early exits.",
            "Old corpus context lacks structural authority; its values remain hints.",
            "Pending-review rules cannot fix values, including Objective and technique rules.",
            "A fixed primary does not classify its set or any other dimension.",
            "Applicability stays open for all clause types, including notes and techniques.",
            "No semantic accuracy, 80-percent target, or model-work reduction is claimed.",
            "Legacy comparison is the pinned structural rule baseline, not a rerun of consensus.",
        ],
    }
    # Finish all computation before creating any output; immutable inputs are never replaced.
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".atlas-taxonomy-",
        dir=destination.parent,
    ) as temporary:
        staging = Path(temporary) / "report"
        staging.mkdir()
        plan_payload = {
            "schema_version": "1.0",
            "diagnostic_only": True,
            "plans": [plan.model_dump(mode="json") for plan in plans],
        }
        _write_json(staging / "taxonomy-decision-plans.json", plan_payload)
        _write_json(staging / "taxonomy-decision-report.json", report)
        resource = files("standards_atlas.resources").joinpath(RESOURCE_DIRECTORY)
        for name in ("rules.yaml", "review.yaml"):
            (staging / name).write_text(
                resource.joinpath(name).read_text(encoding="utf-8"), encoding="utf-8"
            )
        _write_review_csv(staging / "taxonomy-decision-review.csv", plans)
        (staging / "taxonomy-decision-report.md").write_text(
            render_taxonomy_report(report), encoding="utf-8"
        )
        if destination.exists():
            raise ValueError("taxonomy output already exists; refusing to overwrite")
        staging.rename(destination)
    return (
        destination / "taxonomy-decision-report.json",
        destination / "taxonomy-decision-report.md",
    )


def summarize_plans(plans: list[ClauseDecisionPlan]) -> dict[str, Any]:
    attributes = {key: Counter() for key in DECISION_ATTRIBUTES}
    families: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    rules: dict[str, Counter] = defaultdict(Counter)
    documents: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    origin_counts = Counter()
    warnings = Counter()
    for plan in plans:
        key = plan.source.document_key
        family = re.sub(r"(?:-\d+)+$", "", key)
        origin_counts[plan.source.origin] += 1
        warnings.update(plan.warnings)
        for decision in plan.decisions:
            attributes[decision.attribute][decision.state] += 1
            families[family][decision.attribute][decision.state] += 1
            documents[key][decision.attribute][decision.state] += 1
            for rule_id in {item.rule_id for item in decision.evidence}:
                rules[rule_id][decision.state] += 1
    return {
        "selected_clause_count": len(plans),
        "accounted_clause_count": len(plans),
        "origin_counts": dict(origin_counts),
        "attribute_states": attributes,
        "rule_states": dict(rules),
        "document_families": dict(families),
        "documents": dict(documents),
        "warning_counts": dict(warnings),
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _write_review_csv(path: Path, plans: list[ClauseDecisionPlan]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "document_key",
                "clause_id",
                "reference",
                "attribute",
                "state",
                "value",
                "candidates",
                "rules",
                "source_sha256",
                "plan_sha256",
                "review_status",
                "reviewer",
                "reviewed_value",
                "comment",
            )
        )
        for plan in plans:
            for decision in plan.decisions:
                if decision.state == "open":
                    continue
                writer.writerow(
                    (
                        plan.source.document_key,
                        plan.source.clause_id,
                        plan.source.reference,
                        decision.attribute,
                        decision.state,
                        decision.value,
                        "|".join(decision.candidates),
                        "|".join(sorted({item.rule_id for item in decision.evidence})),
                        plan.source_sha256,
                        plan.fingerprint,
                        "pending",
                        "",
                        "",
                        "",
                    )
                )


def render_taxonomy_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Taxonomy decision diagnostics",
        "",
        "Diagnostic only. No inference, acceptance-policy change, canonical adoption "
        "or early exit.",
        "",
        f"Selected/accounted clauses: {summary['selected_clause_count']} / "
        f"{summary['accounted_clause_count']}.",
        f"Rule profile: `{report['rules_id']}@{report['rules_version']}`.",
        "",
        "## Attribute states",
        "",
        "| Attribute | Fixed | Hint | Conflict | Open |",
        "|---|---:|---:|---:|---:|",
    ]
    for attribute, counts in summary["attribute_states"].items():
        lines.append(
            f"| {attribute} | "
            + " | ".join(
                str(counts.get(state, 0)) for state in ("fixed", "hint", "conflict", "open")
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Rule hits (per clause and affected attribute)",
            "",
            "| Rule | Fixed | Hint | Conflict |",
            "|---|---:|---:|---:|",
        ]
    )
    for rule_id, counts in sorted(summary["rule_states"].items()):
        lines.append(
            f"| {rule_id} | "
            + " | ".join(str(counts.get(state, 0)) for state in ("fixed", "hint", "conflict"))
            + " |"
        )
    lines.extend(
        [
            "",
            "## Source and baseline comparison",
            "",
            f"Source origins: `{summary['origin_counts']}`.",
            f"Fixed primary changes relative to legacy: "
            f"{summary['comparison']['fixed_primary_would_change']}.",
            f"Legacy primaries not independently fixed by the plan: "
            f"{summary['comparison']['legacy_primary_not_fixed_by_plan']}.",
            "These are structural diagnostics, not changed production decisions.",
            "",
            "Per-document/family counts, source facts, hashes and exact rule references "
            "are in the JSON artifacts. Review candidates are in the CSV.",
            "",
            "## Review",
            "",
            "The packaged review.yaml is a pending synthetic reference set, not semantic "
            "gold or reviewed accuracy evidence. Review observed source structure and "
            "rule precision independently; model majorities must not become target labels.",
            "No edited CSV is automatically imported or promoted by this command.",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    return "\n".join(lines) + "\n"
