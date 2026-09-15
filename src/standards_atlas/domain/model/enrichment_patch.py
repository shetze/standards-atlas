"""Typed, partial enrichment updates and the shared authority-aware merge."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, model_serializer

from standards_atlas.domain.model.applicability import ClauseApplicability
from standards_atlas.domain.model.clause import Clause, ClauseEnrichments
from standards_atlas.domain.model.context_routing import ContextRouting
from standards_atlas.domain.model.knowledge_state import (
    GeneratedAttribute,
    GenerationMethod,
    KnowledgeStateProvenance,
    paths_overlap,
)
from standards_atlas.domain.model.subject_context import ClauseSubjectContext


class _PartialPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_serializer(mode="wrap")
    def serialize_addressed_fields(self, handler: SerializerFunctionWrapHandler) -> dict:
        return {key: value for key, value in handler(self).items() if key in self.model_fields_set}


class ClauseEnrichmentPatch(_PartialPatch):
    """Partial update of retained clause enrichments.

    Semantic classification is intentionally absent. Applicability, routing and
    subject context are independent first-class dimensions.
    """

    applicability: ClauseApplicability | None = None
    context_routing: ContextRouting | None = None
    subject_context: ClauseSubjectContext | None = None


@dataclass(frozen=True)
class AttributeChange:
    path: str
    status: str
    before: object
    after: object
    reason: str | None = None


@dataclass(frozen=True)
class EnrichmentMergeResult:
    clause: Clause
    changes: tuple[AttributeChange, ...]


_RETAINED_PATHS = {
    "enrichments.applicability",
    "enrichments.context_routing",
    "enrichments.subject_context",
}


def merge_generated_enrichments(
    clause: Clause,
    patch: ClauseEnrichmentPatch,
    attributes: tuple[GeneratedAttribute, ...],
) -> EnrichmentMergeResult:
    by_path = {item.path: item for item in attributes}
    if len(by_path) != len(attributes):
        raise ValueError("duplicate provenance in enrichment patch")
    updates: dict[str, object] = {}
    for field in ("applicability", "context_routing", "subject_context"):
        value = getattr(patch, field)
        if value is not None:
            updates[f"enrichments.{field}"] = value
    if set(updates) != {path for path, item in by_path.items() if item.availability == "known"}:
        raise ValueError("every known patch attribute needs exactly one provenance record")
    if not set(by_path).issubset(_RETAINED_PATHS):
        raise ValueError("unsupported enrichment attribute path")

    state = clause.enrichments.model_dump(mode="python")
    provenance = clause.provenance
    changes: list[AttributeChange] = []

    for path, value in updates.items():
        field = path.removeprefix("enrichments.")
        before = state[field]
        after = _plain(value)
        if provenance.protection(path) and before != after:
            changes.append(AttributeChange(path, "protected", before, after, path))
            continue
        if provenance.protection(path):
            changes.append(AttributeChange(path, "unchanged", before, before, "confirmed/retained"))
            continue
        previous = next(
            (item for item in provenance.generated_attributes if item.path == path), None
        )
        state[field] = after
        provenance = provenance.mark_generated(by_path[path])
        status = "unchanged" if before == after and previous == by_path[path] else "updated"
        changes.append(AttributeChange(path, status, before, after))

    for path, item in by_path.items():
        if item.availability != "unknown" or path in updates:
            continue
        if provenance.availability(path) != "known":
            provenance = provenance.mark_generated(item)
        field = path.removeprefix("enrichments.")
        changes.append(
            AttributeChange(path, "unknown", state[field], state[field], "no usable decision")
        )

    enriched = ClauseEnrichments.model_validate(state)
    return EnrichmentMergeResult(
        clause.model_copy(update={"enrichments": enriched, "provenance": provenance}),
        tuple(changes),
    )


def _plain(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def merge_persisted_enrichments(
    clause: Clause,
    patch: ClauseEnrichmentPatch,
    provenance: KnowledgeStateProvenance,
) -> EnrichmentMergeResult:
    known_paths = {
        f"enrichments.{name}"
        for name in ("applicability", "context_routing", "subject_context")
        if getattr(patch, name) is not None
    }
    incoming = {item.path: item for item in provenance.generated_attributes}
    confirmations = {item.path: item for item in provenance.confirmed_attributes}
    protected = set(confirmations) | set(provenance.unattributed_attributes)
    if not protected.issubset(known_paths):
        raise ValueError("persisted authority requires an explicit known value")

    def current_value(path: str) -> object:
        value: object = clause
        for name in path.split("."):
            value = getattr(value, name)
        return _plain(value)

    def proposed_value(path: str) -> object:
        field = path.removeprefix("enrichments.")
        return _plain(getattr(patch, field))

    for path in protected:
        if path in incoming:
            raise ValueError("persisted generated and protected paths overlap")
        if path in confirmations and clause.provenance.protection(path) == "confirmed":
            if current_value(path) != proposed_value(path):
                raise ValueError(f"conflicting authoritative AtlasData values: {path}")
        incoming[path] = GeneratedAttribute(
            path=path, generator="atlasdata-roundtrip", method=GenerationMethod.IMPORTED
        )
    result = merge_generated_enrichments(clause, patch, tuple(incoming.values()))
    state = result.clause.provenance
    blocked = {item.path for item in result.changes if item.status == "protected"}
    for path, confirmation in confirmations.items():
        if path in blocked or clause.provenance.protection(path) == "confirmed":
            continue
        state = state.confirm_authoritative(path, authority=confirmation.authority)
    unattributed = {
        path
        for path in provenance.unattributed_attributes
        if path not in blocked and not clause.provenance.protection(path)
    }
    if unattributed:
        state = KnowledgeStateProvenance.model_validate(
            {
                **state.model_dump(mode="python"),
                "generated_attributes": tuple(
                    item
                    for item in state.generated_attributes
                    if not any(paths_overlap(item.path, path) for path in unattributed)
                ),
                "unattributed_attributes": tuple(
                    sorted(set(state.unattributed_attributes) | unattributed)
                ),
            }
        )
    return EnrichmentMergeResult(
        result.clause.model_copy(update={"provenance": state}), result.changes
    )
