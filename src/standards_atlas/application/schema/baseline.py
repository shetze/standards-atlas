"""Current bounded schema compatibility policies."""

from __future__ import annotations

from typing import Any

from .policy import SchemaPolicy

SCHEMA_POLICIES: dict[str, SchemaPolicy] = {
    "partial-review-workbench-evidence": SchemaPolicy(
        "partial-review-workbench-evidence", "1.0", ("1.0",), "**/review-evidence.json#workbench"
    ),
    "partial-review-archive": SchemaPolicy(
        "partial-review-archive", "1.0", ("1.0",), "**/review-package.zip#archive-manifest.json"
    ),
    "partial-review-handoff": SchemaPolicy(
        "partial-review-handoff", "1.0", ("1.0",), "**/review-handoff.json"
    ),
    "review-workbench-state": SchemaPolicy(
        "review-workbench-state", "1.0", ("1.0",), "**/workbench/state.json"
    ),
    "partial-review-candidates": SchemaPolicy(
        "partial-review-candidates", "1.0", ("1.0",), "**/preparation/indexes/*/index.json"
    ),
    "partial-review-selection-proposal": SchemaPolicy(
        "partial-review-selection-proposal",
        "1.0",
        ("1.0",),
        "**/preparation/selections/*/selection.json",
    ),
    "partial-review-package": SchemaPolicy(
        "partial-review-package", "1.0", ("1.0",), "**/review-package.json"
    ),
    "partial-review-state": SchemaPolicy(
        "partial-review-state", "1.0", ("1.0",), "**/review-state.json"
    ),
    "partial-review-profile": SchemaPolicy(
        "partial-review-profile", "1.0", ("1.0",), "**/review-profile.yaml"
    ),
    "partial-review-publication": SchemaPolicy(
        "partial-review-publication", "1.1", ("1.1",), "**/review-evidence.json"
    ),
    "partial-qualification-manifest": SchemaPolicy(
        "partial-qualification-manifest", "1.1", ("1.1",), "**/campaign.yaml"
    ),
    "partial-qualification-campaign": SchemaPolicy(
        "partial-qualification-campaign", "2.0", ("2.0",), "**/campaign-plan.json"
    ),
    "partial-qualification-repeat": SchemaPolicy(
        "partial-qualification-repeat", "1.0", ("1.0",), "**/repeat.json"
    ),
    "partial-qualification-evaluation": SchemaPolicy(
        "partial-qualification-evaluation", "1.0", ("1.0",), "**/qualification-evaluation.json"
    ),
    "partial-semantic-reference": SchemaPolicy(
        "partial-semantic-reference", "1.0", ("1.0",), "**/semantic-reference.json"
    ),
    "partial-qualified-activation": SchemaPolicy(
        "partial-qualified-activation", "1.0", ("1.0",), "**/activation.json"
    ),
    "qualification-request-event": SchemaPolicy(
        "qualification-request-event", "1.0", ("1.0",), "**/qualification-events/*.json"
    ),
    "partial-qualification-execution": SchemaPolicy(
        "partial-qualification-execution", "1.0", ("1.0",), "**/execution-report.json"
    ),
    "partial-cascade-report": SchemaPolicy(
        "partial-cascade-report",
        "1.1",
        ("1.1",),
        "**/partial-cascade-report.json",
    ),
    "partial-cascade-audit": SchemaPolicy(
        "partial-cascade-audit",
        "1.0",
        ("1.0",),
        "**/partial-cascade-audit.json",
    ),
    "taxonomy-pilot-readiness": SchemaPolicy(
        "taxonomy-pilot-readiness",
        "1.0",
        ("1.0",),
        "**/pilot-readiness.json",
    ),
    "taxonomy-readiness-cases": SchemaPolicy(
        "taxonomy-readiness-cases",
        "1.0",
        ("1.0",),
        "resources/semantic/qualification/taxonomy-readiness-v1/cases.yaml",
    ),
    "semantic-readiness-checks": SchemaPolicy(
        "semantic-readiness-checks",
        "1.0",
        ("1.0",),
        "**/readiness-checks.json",
    ),
    "semantic-readiness-evaluation": SchemaPolicy(
        "semantic-readiness-evaluation",
        "1.0",
        ("1.0",),
        "**/semantic-readiness.json",
    ),
    "mixed-consensus": SchemaPolicy(
        "mixed-consensus", "1.0", ("1.0",), "**/mixed-consensus-report.json"
    ),
    "partial-cascade-run": SchemaPolicy(
        "partial-cascade-run", "1.0", ("1.0",), "**/partial-cascade-*.json"
    ),
    "partial-request-plan": SchemaPolicy(
        "partial-request-plan", "1.1", ("1.1",), "**/partial-request-plan.json"
    ),
    "partial-semantic-observation": SchemaPolicy(
        "partial-semantic-observation", "1.1", ("1.1",), "**/partial-observation.json"
    ),
    "partial-proposal-run": SchemaPolicy(
        "partial-proposal-run", "1.0", ("1.0",), "**/partial-run-*.json"
    ),
    "source-structure": SchemaPolicy(
        "source-structure", "1.0", ("1.0",), "clause-descriptor.source_structure"
    ),
    "clause-decision-plan": SchemaPolicy(
        "clause-decision-plan", "1.0", ("1.0",), "**/taxonomy-decision-plans.json"
    ),
    "taxonomy-decision-report": SchemaPolicy(
        "taxonomy-decision-report", "1.0", ("1.0",), "**/taxonomy-decision-report.json"
    ),
    "taxonomy-decision-rules": SchemaPolicy(
        "taxonomy-decision-rules", 1, (1,), "resources/semantic/taxonomy-decisions/**/rules.yaml"
    ),
    "taxonomy-decision-review": SchemaPolicy(
        "taxonomy-decision-review", 1, (1,), "resources/semantic/taxonomy-decisions/**/review.yaml"
    ),
    "cascade-provenance": SchemaPolicy(
        "cascade-provenance", "1.6", ("1.6",), "**/cascade-provenance.json"
    ),
    "cascade-replay": SchemaPolicy("cascade-replay", "1.0", ("1.0",), "**/cascade-replay.json"),
    "qualification-request-timing": SchemaPolicy(
        "qualification-request-timing", "1.0", ("1.0",), "**/request-timing.json"
    ),
    "qualification-matrix-report": SchemaPolicy(
        "qualification-matrix-report", "1.1", ("1.1",), "**/qualification-matrix.json"
    ),
    "qualification-consensus": SchemaPolicy(
        "qualification-consensus", "5.0", ("5.0",), "**/consensus-report.json"
    ),
    "golden-corpus-proposal": SchemaPolicy(
        "golden-corpus-proposal", "4.0", ("4.0",), "**/golden-corpus-proposal.yaml"
    ),
    "cbox-enrichments": SchemaPolicy(
        "cbox-enrichments", "1.0", ("1.0",), "clause-descriptor.enrichment_context"
    ),
    "cbox-report": SchemaPolicy("cbox-report", "1.0", ("1.0",), "local/**/cbox*.json"),
    "atlasdata-enrichments": SchemaPolicy(
        "atlasdata-enrichments", "1.2", ("1.2",), "data/enrichments/*.yaml"
    ),
    "knowledge-evidence": SchemaPolicy(
        "knowledge-evidence", "1.0", ("1.0",), ".atlas/data/knowledge-evidence/*.json"
    ),
    "atlasdata-knowledge-report": SchemaPolicy(
        "atlasdata-knowledge-report", "1.0", ("1.0",), "local/**/atlasdata-knowledge*.json"
    ),
    "engineering-document": SchemaPolicy(
        "engineering-document", 9, (9,), ".atlas/data/documents/*.json"
    ),
    "knowledge-adoption-batch": SchemaPolicy(
        "knowledge-adoption-batch", "1.1", ("1.1",), "local/**/knowledge-adoption-batch.json"
    ),
    "knowledge-adoption-report": SchemaPolicy(
        "knowledge-adoption-report", "1.0", ("1.0",), "local/**/knowledge-adoption-report.json"
    ),
    "standards-manifest": SchemaPolicy("standards-manifest", 2, (2,), "manifests/*.yaml"),
    "qualification-matrix-manifest": SchemaPolicy(
        "qualification-matrix-manifest", "1.6", ("1.6",), "manifests/*.yaml"
    ),
    "semantic-task-resource": SchemaPolicy(
        "semantic-task-resource", 1, (1,), "resources/semantic/tasks/**/task.yaml"
    ),
    "semantic-profile-resource": SchemaPolicy(
        "semantic-profile-resource", 1, (1,), "resources/semantic/profiles/**/profile.yaml"
    ),
    "ontology-resource": SchemaPolicy(
        "ontology-resource", 1, (1,), "resources/ontologies/**/ontology.yaml"
    ),
    "formal-ontology-resource": SchemaPolicy(
        "formal-ontology-resource", 1, (1,), "resources/formal_ontologies/**/ontology.yaml"
    ),
    "formal-semantic-projection": SchemaPolicy(
        "formal-semantic-projection", 1, (1,), ".atlas/data/formal-semantic-projections/*.json"
    ),
    "semantic-extraction": SchemaPolicy(
        "semantic-extraction", 1, (1,), ".atlas/data/semantic-extractions/*.json"
    ),
    "structural-taxonomy-resource": SchemaPolicy(
        "structural-taxonomy-resource",
        1,
        (1,),
        "resources/structure-taxonomies/**/taxonomy.yaml",
    ),
}

# Compatibility alias for code/docs created by the baseline slice.
SCHEMA_BASELINES = SCHEMA_POLICIES
SchemaBaseline = SchemaPolicy


def require_supported_schema(family: str, value: Any) -> None:
    """Validate that ``value`` is inside the bounded reader support window."""
    SCHEMA_POLICIES[family].require_readable(value)


def require_current_schema(family: str, value: Any) -> None:
    """Validate writer-side current schema output."""
    SCHEMA_POLICIES[family].require_current_for_write(value)
