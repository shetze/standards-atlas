"""Current bounded schema compatibility policies."""

from __future__ import annotations

from typing import Any

from .policy import SchemaPolicy

SCHEMA_POLICIES: dict[str, SchemaPolicy] = {
    "partial-request-plan": SchemaPolicy(
        "partial-request-plan", "1.0", ("1.0",), "**/partial-request-plan.json"
    ),
    "partial-semantic-observation": SchemaPolicy(
        "partial-semantic-observation", "1.0", ("1.0",), "**/partial-observation.json"
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
        "cascade-provenance", "1.6", ("1.5", "1.6"), "**/cascade-provenance.json"
    ),
    "cascade-replay": SchemaPolicy("cascade-replay", "1.0", ("1.0",), "**/cascade-replay.json"),
    "qualification-request-timing": SchemaPolicy(
        "qualification-request-timing", "1.0", ("1.0",), "**/request-timing.json"
    ),
    "qualification-matrix-report": SchemaPolicy(
        "qualification-matrix-report", "1.1", ("1.0", "1.1"), "**/qualification-matrix.json"
    ),
    "qualification-consensus": SchemaPolicy(
        "qualification-consensus", "5.0", ("4.0", "5.0"), "**/consensus-report.json"
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
        "engineering-document", 9, (8, 9), ".atlas/data/documents/*.json"
    ),
    "knowledge-adoption-batch": SchemaPolicy(
        "knowledge-adoption-batch", "1.0", ("1.0",), "local/**/knowledge-adoption-batch.json"
    ),
    "knowledge-adoption-report": SchemaPolicy(
        "knowledge-adoption-report", "1.0", ("1.0",), "local/**/knowledge-adoption-report.json"
    ),
    "standards-manifest": SchemaPolicy("standards-manifest", 2, (2,), "manifests/*.yaml"),
    "qualification-matrix-manifest": SchemaPolicy(
        "qualification-matrix-manifest", "1.6", ("1.5", "1.6"), "manifests/*.yaml"
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
