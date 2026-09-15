"""Current bounded schema compatibility policies."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import policy as compatibility
from .policy import CompatibilityPhase, SchemaPolicy

SCHEMA_POLICIES: dict[str, SchemaPolicy] = {
    "review-source-manifest": SchemaPolicy(
        "review-source-manifest", 1, (1,), "cfg/evaluation/review/*.yaml"
    ),
    "review-profile": SchemaPolicy("review-profile", 1, (1,), "**/review-profile.yaml"),
    "review-package": SchemaPolicy("review-package", 1, (1,), "**/review-package.json"),
    "review-state": SchemaPolicy("review-state", 1, (1,), "**/review-state.json"),
    "review-publication": SchemaPolicy("review-publication", 1, (1,), "**/review-evidence.json"),
    "review-reference-suite": SchemaPolicy(
        "review-reference-suite", 1, (1,), "**/{development,holdout}.yaml"
    ),
    "review-candidates": SchemaPolicy(
        "review-candidates", 1, (1,), "**/preparation/indexes/*/index.json"
    ),
    "review-selection-proposal": SchemaPolicy(
        "review-selection-proposal", 1, (1,), "**/preparation/selections/*/selection.json"
    ),
    "review-archive": SchemaPolicy(
        "review-archive", 1, (1,), "**/review-package.zip#archive-manifest.json"
    ),
    "review-workbench-state": SchemaPolicy(
        "review-workbench-state", 1, (1,), "**/workbench/state.json"
    ),
    "review-workbench-evidence": SchemaPolicy(
        "review-workbench-evidence", 1, (1,), "**/review-evidence.json#workbench"
    ),
    "source-structure": SchemaPolicy(
        "source-structure", "1.0", ("1.0",), "clause-descriptor.source_structure"
    ),
    "cascade-provenance": SchemaPolicy("cascade-provenance", 1, (1,), "**/cascade-provenance.json"),
    "cascade-replay": SchemaPolicy("cascade-replay", "1.0", ("1.0",), "**/cascade-replay.json"),
    "qualification-request-timing": SchemaPolicy(
        "qualification-request-timing", "1.0", ("1.0",), "**/request-timing.json"
    ),
    "qualification-matrix-report": SchemaPolicy(
        "qualification-matrix-report", 1, (1,), "**/qualification-matrix.json"
    ),
    "qualification-consensus": SchemaPolicy(
        "qualification-consensus", 1, (1,), "**/consensus-report.json"
    ),
    "golden-corpus-proposal": SchemaPolicy(
        "golden-corpus-proposal", 1, (1,), "**/golden-corpus-proposal.yaml"
    ),
    "cbox-enrichments": SchemaPolicy(
        "cbox-enrichments", "1.0", ("1.0",), "clause-descriptor.enrichment_context"
    ),
    "cbox-report": SchemaPolicy("cbox-report", "1.0", ("1.0",), "local/**/cbox*.json"),
    "atlasdata-enrichments": SchemaPolicy(
        "atlasdata-enrichments", 1, (1,), "data/enrichments/*.yaml"
    ),
    "knowledge-evidence": SchemaPolicy(
        "knowledge-evidence", 1, (1,), ".atlas/data/knowledge-evidence/*.json"
    ),
    "atlasdata-knowledge-report": SchemaPolicy(
        "atlasdata-knowledge-report", 1, (1,), "local/**/atlasdata-knowledge*.json"
    ),
    "engineering-document": SchemaPolicy(
        "engineering-document", 1, (1,), ".atlas/data/documents/*.json"
    ),
    "context-adoption-batch": SchemaPolicy(
        "context-adoption-batch", 1, (1,), "local/**/context-adoption-batch.json"
    ),
    "context-adoption-report": SchemaPolicy(
        "context-adoption-report", 1, (1,), "local/**/context-adoption-report.json"
    ),
    "standards-manifest": SchemaPolicy("standards-manifest", 2, (2,), "manifests/*.yaml"),
    "qualification-matrix-manifest": SchemaPolicy(
        "qualification-matrix-manifest", 1, (1,), "manifests/*.yaml"
    ),
    "semantic-task-resource": SchemaPolicy(
        "semantic-task-resource", 1, (1,), "resources/semantic/tasks/**/task.yaml"
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
    "document-knowledge-proposal": SchemaPolicy(
        "document-knowledge-proposal",
        1,
        (1,),
        ".atlas/data/knowledge-proposals/*/*.json",
    ),
    "assertion-golden-suite": SchemaPolicy(
        "assertion-golden-suite",
        1,
        (1,),
        "local/review/assertions/**/assertion-golden-suite.{yaml,yml,json}",
    ),
    "assertion-qualification-report": SchemaPolicy(
        "assertion-qualification-report",
        1,
        (1,),
        "local/evaluation/**/assertion-qualification*.json",
    ),
    "structural-taxonomy-resource": SchemaPolicy(
        "structural-taxonomy-resource",
        1,
        (1,),
        "resources/structure-taxonomies/**/taxonomy.yaml",
    ),
    "complypack-workspace-manifest": SchemaPolicy(
        "complypack-workspace-manifest",
        "1.0",
        ("1.0",),
        "local/exports/complypack/**/workspace-manifest.yaml",
    ),
    "complytime-evaluation-feedback-manifest": SchemaPolicy(
        "complytime-evaluation-feedback-manifest",
        "1.0",
        ("1.0",),
        "local/**/evaluation-feedback*.json",
    ),
    "governance-bundle-manifest": SchemaPolicy(
        "governance-bundle-manifest",
        "1.0",
        ("1.0",),
        "local/exports/complypack/**/governance/manifest.yaml",
    ),
    "governance-bundle-traceability": SchemaPolicy(
        "governance-bundle-traceability",
        "1.0",
        ("1.0",),
        "local/exports/complypack/**/governance/traceability.json",
    ),
    "qualification-archive-receipt": SchemaPolicy(
        "qualification-archive-receipt",
        "1.0",
        ("1.0",),
        "**/qualification-archive-receipt.json",
    ),
    "gemara-control-traceability": SchemaPolicy(
        "gemara-control-traceability",
        "2.0",
        ("2.0",),
        "**/*.traceability.json#control",
    ),
    "gemara-traceability": SchemaPolicy(
        "gemara-traceability",
        "1.0",
        ("1.0",),
        "**/*.traceability.json#guidance",
    ),
    "governance-policy-scaffold": SchemaPolicy(
        "governance-policy-scaffold",
        2,
        (2,),
        "local/review/governance/**/*.scaffold.json",
    ),
    "alignment-result": SchemaPolicy(
        "alignment-result",
        2,
        (2,),
        ".atlas/data/alignments/*/alignment.json",
    ),
    "alignment-overrides": SchemaPolicy(
        "alignment-overrides",
        1,
        (1,),
        "local/review/alignment/*/overrides.yaml",
    ),
    "engineering-construction-contract": SchemaPolicy(
        "engineering-construction-contract",
        1,
        (1,),
        ".atlas/data/construction/*/contract.json",
    ),
    "formula-transcription": SchemaPolicy(
        "formula-transcription",
        1,
        (1,),
        ".atlas/data/enrichments/formula-transcriptions/*.json",
    ),
    "normalized-document": SchemaPolicy(
        "normalized-document",
        10,
        (10,),
        ".atlas/data/normalized/*/document.json#metadata",
    ),
    "normalization-run": SchemaPolicy(
        "normalization-run",
        1,
        (1,),
        ".atlas/data/normalized/*/run.json",
    ),
    "reference-candidate-document": SchemaPolicy(
        "reference-candidate-document",
        2,
        (2,),
        ".atlas/data/reference-candidates/*/document.json#metadata",
    ),
    "normalization-golden-case": SchemaPolicy(
        "normalization-golden-case",
        1,
        (1,),
        "tests/golden_corpus/cases/*/manifest.json",
    ),
    "normalization-qualification-run-report": SchemaPolicy(
        "normalization-qualification-run-report",
        1,
        (1,),
        ".atlas/data/qualification/runs/*/report.json",
    ),
    "clause-evaluation-annotation": SchemaPolicy(
        "clause-evaluation-annotation",
        1,
        (1,),
        "**/annotations/**/*.yaml",
    ),
    "evaluation-corpus": SchemaPolicy(
        "evaluation-corpus",
        1,
        (1,),
        "**/corpus.yaml",
    ),
    "applicability-detail-hitl-consensus": SchemaPolicy(
        "applicability-detail-hitl-consensus",
        "1.1",
        ("1.1",),
        "local/**/applicability-detail-hitl-consensus*.json",
    ),
    "applicability-detail-selection": SchemaPolicy(
        "applicability-detail-selection",
        "1.0",
        ("1.0",),
        "**/applicability-detail-selection*.json",
    ),
    "applicability-detail-enrichment-report": SchemaPolicy(
        "applicability-detail-enrichment-report",
        "1.0",
        ("1.0",),
        "**/applicability-detail-enrichment*.json",
    ),
    "applicability-detail-failure-report": SchemaPolicy(
        "applicability-detail-failure-report",
        "1.0",
        ("1.0",),
        "**/applicability-detail-failures*.json",
    ),
    "applicability-policy-evaluation-report": SchemaPolicy(
        "applicability-policy-evaluation-report",
        "1.0",
        ("1.0",),
        "**/applicability-policy-evaluation*.json",
    ),
    "applicability-policy-run-state": SchemaPolicy(
        "applicability-policy-run-state",
        "1.1",
        ("1.1",),
        "**/applicability-policy-state*.json",
    ),
    "applicability-policy-replay-report": SchemaPolicy(
        "applicability-policy-replay-report",
        "1.0",
        ("1.0",),
        "**/applicability-policy-replay*.json",
    ),
    "applicability-policy-run-report": SchemaPolicy(
        "applicability-policy-run-report",
        "1.1",
        ("1.1",),
        "**/applicability-policy-run*.json",
    ),
    "applicability-qualification-report": SchemaPolicy(
        "applicability-qualification-report", 1, (1,), "**/applicability-qualification.json"
    ),
    "qualification-coverage": SchemaPolicy(
        "qualification-coverage",
        "1.0",
        ("1.0",),
        "**/qualification-coverage.json",
    ),
    "qualification-run-selection": SchemaPolicy(
        "qualification-run-selection",
        "1.2",
        ("1.2",),
        "**/selection.json",
    ),
    "benchmark-manifest": SchemaPolicy(
        "benchmark-manifest",
        1,
        (1,),
        "**/benchmark*.yaml",
    ),
    "governance-selection-profile": SchemaPolicy(
        "governance-selection-profile",
        1,
        (1,),
        "local/governance/*.yaml",
    ),
    "governance-subject-group-profile": SchemaPolicy(
        "governance-subject-group-profile",
        1,
        (1,),
        "resources/governance/subject-groups/**/profile.yaml",
    ),
    "workflow-run-report": SchemaPolicy(
        "workflow-run-report",
        4,
        (4,),
        ".atlas/work/workflow/**/report.json",
    ),
    "reviewed-alignment-integrity": SchemaPolicy(
        "reviewed-alignment-integrity",
        1,
        (1,),
        "local/review/alignment/*/reviewed.integrity.json",
    ),
    "docling-conversion-metadata": SchemaPolicy(
        "docling-conversion-metadata",
        1,
        (1,),
        ".atlas/data/docling/*/conversion.json",
    ),
    "method-technique-index": SchemaPolicy(
        "method-technique-index",
        1,
        (1,),
        ".atlas/data/normalized/*/methods-and-techniques.json",
    ),
    "workflow-input-marker": SchemaPolicy(
        "workflow-input-marker",
        1,
        (1,),
        ".atlas/work/workflow/input-state/*.json",
    ),
    "workflow-step-marker": SchemaPolicy(
        "workflow-step-marker",
        1,
        (1,),
        ".atlas/work/workflow/**/*.json#step-fingerprint",
    ),
    "workflow-fresh-repetition-marker": SchemaPolicy(
        "workflow-fresh-repetition-marker",
        1,
        (1,),
        ".atlas/work/workflow/fresh-repetitions/*",
    ),
    "enrichment-baseline": SchemaPolicy(
        "enrichment-baseline",
        1,
        (1,),
        ".atlas/data/evaluation/baselines/enrichments/**/*.zip#baseline.json",
    ),
    "enrichment-baseline-manifest": SchemaPolicy(
        "enrichment-baseline-manifest",
        1,
        (1,),
        ".atlas/data/evaluation/baselines/enrichments/**/*.zip#manifest.json",
    ),
    "evaluation-matrix-summary": SchemaPolicy(
        "evaluation-matrix-summary",
        1,
        (1,),
        "local/evaluation/**/matrix-summary*.json",
    ),
    "normalization-quality-report": SchemaPolicy(
        "normalization-quality-report",
        1,
        (1,),
        "local/evaluation/**/qualification.json#normalization-quality",
    ),
    "qualification-analysis-metrics": SchemaPolicy(
        "qualification-analysis-metrics",
        "1.5",
        ("1.5",),
        "**/qualification-analysis-metrics.json",
    ),
    "qualification-analysis-archive-manifest": SchemaPolicy(
        "qualification-analysis-archive-manifest",
        "1.5",
        ("1.5",),
        "**/qualification-run-*.zip#archive-manifest.json",
    ),
    "qualification-run-metadata": SchemaPolicy(
        "qualification-run-metadata",
        "1.5",
        ("1.5",),
        "**/qualification-run-*.zip#qualification-run-metadata.json",
    ),
    "qualification-run-index": SchemaPolicy(
        "qualification-run-index",
        "1.0",
        ("1.0",),
        "local/evaluation/qualification-run-index.json",
    ),
    "challenger-sample-selection": SchemaPolicy(
        "challenger-sample-selection",
        "1.0",
        ("1.0",),
        "**/challenger-sample-selection.json",
    ),
    "challenger-comparison": SchemaPolicy(
        "challenger-comparison",
        "1.0",
        ("1.0",),
        "**/challenger-comparison.json",
    ),
    "semantic-evaluation": SchemaPolicy(
        "semantic-evaluation",
        1,
        (1,),
        "**/evaluation.yaml",
    ),
    "context-run-report": SchemaPolicy(
        "context-run-report",
        1,
        (1,),
        ".atlas/data/evaluation/context-routing/*-run.json",
    ),
    "applicability-golden-corpus": SchemaPolicy(
        "applicability-golden-corpus",
        "3.0",
        ("3.0",),
        "local/review/applicability/**/applicability-golden-corpus.yaml",
    ),
    "applicability-prediction-snapshot": SchemaPolicy(
        "applicability-prediction-snapshot",
        "2.0",
        ("2.0",),
        "**/applicability-predictions.json",
    ),
}


def validate_schema_registry(
    policies: Mapping[str, SchemaPolicy] | None = None,
    *,
    phase: CompatibilityPhase | None = None,
) -> None:
    """Check the concrete registry, never widen it to fill a future Stable window."""
    policies = SCHEMA_POLICIES if policies is None else policies
    phase = compatibility.CURRENT_COMPATIBILITY_PHASE if phase is None else phase
    if not isinstance(phase, CompatibilityPhase):
        raise ValueError("registry requires an explicit CompatibilityPhase")
    if not policies:
        raise ValueError("schema registry cannot be empty")
    for family, policy in policies.items():
        _validate_registration(family, policy, phase)


def _validate_registration(family: str, policy: SchemaPolicy, phase: CompatibilityPhase) -> None:
    if not isinstance(policy, SchemaPolicy) or family != policy.family:
        raise ValueError(f"schema registry key differs from policy family: {family!r}")
    # Recheck frozen instances, including invalid object-level mutations in callers/tests.
    policy.__post_init__()
    if policy.phase is not phase:
        raise ValueError(f"schema registry phase differs for {family!r}: expected {phase.value}")


def _registered_policy(family: str) -> SchemaPolicy:
    try:
        policy = SCHEMA_POLICIES[family]
    except KeyError as exc:
        raise ValueError(f"unregistered schema family: {family!r}") from exc
    _validate_registration(family, policy, compatibility.CURRENT_COMPATIBILITY_PHASE)
    return policy


def require_supported_schema(family: str, value: Any) -> None:
    """Validate an explicit, type-exact marker against the active reader policy."""
    _registered_policy(family).require_readable(value)


def require_current_schema(family: str, value: Any) -> None:
    """Validate actual writer output; never normalize or replace its version."""
    _registered_policy(family).require_current_for_write(value)


def require_current_payload(family: str, payload: Mapping[str, Any]) -> None:
    """Guard a serialized envelope before any write, retaining its exact hash input.

    This checks only this family's marker. Nested independent contracts must be
    guarded explicitly; arbitrary attachments are not recursively 'certified'.
    """
    if not isinstance(payload, Mapping) or "schema_version" not in payload:
        raise ValueError(f"{family} writer payload requires an explicit schema_version")
    require_current_schema(family, payload["schema_version"])


validate_schema_registry()
