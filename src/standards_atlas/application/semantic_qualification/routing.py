"""Consume persisted deterministic routing plans during task qualification."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.routing import (
    RoutingDisposition,
    RoutingExecutionPolicy,
    SemanticRoutingArtifactRepository,
)


class QualificationRoutingConfig(BaseModel):
    """Routing filter attached to a split semantic qualification manifest."""

    model_config = ConfigDict(frozen=True)

    contract_id: str = Field(min_length=1)
    contract_version: str = Field(min_length=1)
    minimum_disposition: RoutingDisposition = RoutingDisposition.OPTIONAL
    include_unrouted: bool = False


def routed_example_ids(
    examples: Iterable[EvaluationExample],
    *,
    task: str,
    config: QualificationRoutingConfig,
    repository: SemanticRoutingArtifactRepository,
) -> tuple[str, ...]:
    """Return corpus example IDs admitted by persisted routing decisions."""

    policy = RoutingExecutionPolicy(
        minimum_disposition=config.minimum_disposition,
        include_unrouted=config.include_unrouted,
    )
    artifacts = {}
    selected: list[str] = []
    for example in examples:
        context = dict(example.input.get("context", {}))
        document_key = str(context.get("document_key") or "").strip()
        clause_id = str(context.get("clause_id") or example.id).strip()
        if not document_key:
            raise ValueError(
                f"routing-enabled qualification example {example.id!r} has no document_key"
            )
        artifact = artifacts.get(document_key)
        if artifact is None:
            try:
                artifact = repository.load(
                    document_key,
                    config.contract_id,
                    config.contract_version,
                )
            except FileNotFoundError as exc:
                raise ValueError(
                    "routing-enabled qualification requires a persisted routing artifact for "
                    f"{document_key!r}; run deterministic routing first"
                ) from exc
            artifacts[document_key] = artifact
        record = next((item for item in artifact.clauses if item.clause_id == clause_id), None)
        if record is None:
            if config.include_unrouted:
                selected.append(example.id)
            continue
        if policy.allows(record.plan.decision_for(task)):
            selected.append(example.id)
    return tuple(selected)


def build_routing_qualification_summary(
    examples: Iterable[EvaluationExample],
    *,
    task: str,
    config: QualificationRoutingConfig,
    repository: SemanticRoutingArtifactRepository,
) -> dict[str, object]:
    """Summarize deterministic routing admission for one qualification task."""

    policy = RoutingExecutionPolicy(
        minimum_disposition=config.minimum_disposition,
        include_unrouted=config.include_unrouted,
    )
    artifacts = {}
    disposition_counts = {
        RoutingDisposition.REQUIRED.value: 0,
        RoutingDisposition.PREFERRED.value: 0,
        RoutingDisposition.OPTIONAL.value: 0,
        RoutingDisposition.SKIP.value: 0,
        "unrouted": 0,
    }
    admitted = 0
    skipped = 0
    document_keys: set[str] = set()
    for example in examples:
        context = dict(example.input.get("context", {}))
        document_key = str(context.get("document_key") or "").strip()
        clause_id = str(context.get("clause_id") or example.id).strip()
        if not document_key:
            raise ValueError(
                f"routing-enabled qualification example {example.id!r} has no document_key"
            )
        document_keys.add(document_key)
        artifact = artifacts.get(document_key)
        if artifact is None:
            try:
                artifact = repository.load(
                    document_key,
                    config.contract_id,
                    config.contract_version,
                )
            except FileNotFoundError as exc:
                raise ValueError(
                    "routing-enabled qualification requires a persisted routing artifact for "
                    f"{document_key!r}; run deterministic routing first"
                ) from exc
            artifacts[document_key] = artifact
        record = next((item for item in artifact.clauses if item.clause_id == clause_id), None)
        decision = record.plan.decision_for(task) if record is not None else None
        if decision is None:
            disposition_counts["unrouted"] += 1
        else:
            disposition_counts[decision.disposition.value] += 1
        if policy.allows(decision):
            admitted += 1
        else:
            skipped += 1

    return {
        "task": task,
        "contract_id": config.contract_id,
        "contract_version": config.contract_version,
        "minimum_disposition": config.minimum_disposition.value,
        "include_unrouted": config.include_unrouted,
        "example_count": admitted + skipped,
        "admitted": admitted,
        "skipped": skipped,
        "dispositions": disposition_counts,
        "document_count": len(document_keys),
        "document_keys": sorted(document_keys),
    }
