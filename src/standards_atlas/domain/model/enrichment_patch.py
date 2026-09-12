"""Typed, partial enrichment updates and the shared authority-aware merge."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, model_serializer

from standards_atlas.domain.model.clause import Clause, ClauseEnrichments
from standards_atlas.domain.model.context_routing import ContextRouting
from standards_atlas.domain.model.knowledge_state import (
    GeneratedAttribute,
    GenerationMethod,
    KnowledgeStateProvenance,
    paths_overlap,
    sparse_semantic_validation_context,
)
from standards_atlas.domain.model.semantic_classification import (
    ApplicabilityFunction,
    KnowledgeKind,
    ProcessFunction,
    RoleRelation,
    RoleRelationType,
    StatementFunction,
)
from standards_atlas.domain.model.subject_context import ClauseSubjectContext


class _PartialPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_serializer(mode="wrap")
    def serialize_addressed_fields(self, handler: SerializerFunctionWrapHandler) -> dict:
        """Keep omission semantics when an adoption batch is serialized and read back."""
        return {key: value for key, value in handler(self).items() if key in self.model_fields_set}


class SemanticEnrichmentPatch(_PartialPatch):
    """Omitted fields are untouched; False and empty tuples are explicit values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    primary_function: StatementFunction | None = None
    primary_knowledge_kind: KnowledgeKind | None = None
    primary_process_function: ProcessFunction | None = None
    statement_functions: tuple[StatementFunction, ...] = ()
    knowledge_kinds: tuple[KnowledgeKind, ...] = ()
    process_functions: tuple[ProcessFunction, ...] = ()
    applicability_present: bool = False
    applicability_functions: tuple[ApplicabilityFunction, ...] = ()
    role_semantics_present: bool = False
    role_relation_types: tuple[RoleRelationType, ...] = ()
    role_relations: tuple[RoleRelation, ...] = ()


class ClauseEnrichmentPatch(_PartialPatch):
    model_config = ConfigDict(frozen=True, extra="forbid")

    semantic: SemanticEnrichmentPatch | None = None
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


_SEMANTIC_GROUPS = (
    ("statement_functions", "primary_function"),
    ("knowledge_kinds", "primary_knowledge_kind"),
    ("process_functions", "primary_process_function"),
    ("applicability_present", "applicability_functions"),
    ("role_semantics_present", "role_relation_types", "role_relations"),
)


def merge_generated_enrichments(
    clause: Clause,
    patch: ClauseEnrichmentPatch,
    attributes: tuple[GeneratedAttribute, ...],
) -> EnrichmentMergeResult:
    """Merge addressed groups, protecting confirmations and validating invariants.

    Unknown assessments may record absence of a decision, but never replace a
    known value. Coupled dimensions are atomic; an authority conflict in one
    group does not block unrelated attributes. This function performs no I/O.
    """
    by_path = {item.path: item for item in attributes}
    if len(by_path) != len(attributes):
        raise ValueError("duplicate provenance in enrichment patch")
    updates: dict[str, object] = {}
    if patch.semantic is not None:
        updates.update(
            {
                f"enrichments.semantic.{field}": getattr(patch.semantic, field)
                for field in patch.semantic.model_fields_set
            }
        )
    for field in ("context_routing", "subject_context"):
        if getattr(patch, field) is not None:
            updates[f"enrichments.{field}"] = getattr(patch, field)
    if set(updates) != {path for path, item in by_path.items() if item.availability == "known"}:
        raise ValueError("every known patch attribute needs exactly one provenance record")
    allowed = {f"enrichments.semantic.{name}" for name in SemanticEnrichmentPatch.model_fields}
    allowed.update(("enrichments.context_routing", "enrichments.subject_context"))
    if not set(by_path).issubset(allowed):
        raise ValueError("unsupported enrichment attribute path")

    groups = [tuple(f"enrichments.semantic.{name}" for name in group) for group in _SEMANTIC_GROUPS]
    groups.extend((("enrichments.context_routing",), ("enrichments.subject_context",)))
    state = clause.enrichments.model_dump(mode="python")
    provenance = clause.provenance
    changes: list[AttributeChange] = []

    def get(path: str) -> object:
        parts = path.split(".")[1:]
        value = state
        for part in parts:
            value = value[part]
        return value

    def put(path: str, value: object) -> None:
        parts = path.split(".")[1:]
        target = state
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = _plain(value)

    for group in groups:
        addressed = [path for path in group if path in updates]
        # Clearing a coupled dimension also clears stale dependents, with the
        # same derivation record. No unknown decision is converted to False.
        for presence, dependents in (
            ("applicability_present", ("applicability_functions",)),
            ("role_semantics_present", ("role_relation_types", "role_relations")),
        ):
            presence_path = f"enrichments.semantic.{presence}"
            if presence_path in addressed and updates[presence_path] is False:
                for dependent in dependents:
                    path = f"enrichments.semantic.{dependent}"
                    if path in updates and updates[path]:
                        raise ValueError("negative presence conflicts with supplied details")
                    if path not in updates:
                        sparse = by_path[presence_path].generator == "taxonomy-partial-adoption-v1"
                        if sparse and not get(path):
                            # An already empty, unobserved dependency is not a new result.
                            continue
                        updates[path] = ()
                        by_path[path] = by_path[presence_path].model_copy(
                            update={"path": path, **({"availability": "unknown"} if sparse else {})}
                        )
                    if path not in addressed:
                        addressed.append(path)
        # A replaced set must not retain a stale primary not contained in it.
        for members, primary in (
            ("statement_functions", "primary_function"),
            ("knowledge_kinds", "primary_knowledge_kind"),
            ("process_functions", "primary_process_function"),
        ):
            path = f"enrichments.semantic.{members}"
            primary_path = f"enrichments.semantic.{primary}"
            if (
                path in addressed
                and primary_path not in addressed
                and get(primary_path) is not None
            ):
                if get(primary_path) not in updates[path]:
                    updates[primary_path] = None
                    if (
                        primary == "primary_process_function"
                        or by_path[path].generator == "taxonomy-partial-adoption-v1"
                    ):
                        # Clearing an invalidated primary is not a measured null
                        # decision. Retain an explicit unknown assessment when
                        # supplied; otherwise derive only its unavailability.
                        source = by_path.get(primary_path, by_path[path])
                        by_path[primary_path] = source.model_copy(
                            update={"path": primary_path, "availability": "unknown"}
                        )
                    else:
                        by_path[primary_path] = by_path[path].model_copy(
                            update={"path": primary_path}
                        )
                    addressed.append(primary_path)
        coupled_conflicts = []
        # A new sparse primary cannot implicitly repair a stale complete set.
        # Invalidate only unprotected older membership; never weaken authority.
        for primary, members in (
            ("primary_function", "statement_functions"),
            ("primary_knowledge_kind", "knowledge_kinds"),
            ("primary_process_function", "process_functions"),
        ):
            primary_path = f"enrichments.semantic.{primary}"
            members_path = f"enrichments.semantic.{members}"
            if (
                primary_path in addressed
                and updates[primary_path] is not None
                and by_path[primary_path].generator == "taxonomy-partial-adoption-v1"
                and members_path not in addressed
                and updates[primary_path] not in get(members_path)
            ):
                if provenance.protection(members_path):
                    coupled_conflicts.append(members_path)
                elif get(members_path) or provenance.availability(members_path) == "known":
                    updates[members_path] = ()
                    by_path[members_path] = by_path[primary_path].model_copy(
                        update={"path": members_path, "availability": "unknown"}
                    )
                    addressed.append(members_path)
        conflicts = [
            path
            for path in addressed
            if provenance.protection(path) and get(path) != _plain(updates[path])
        ]
        conflicts.extend(coupled_conflicts)
        for path in addressed:
            before, after = get(path), _plain(updates[path])
            if conflicts:
                changes.append(
                    AttributeChange(path, "protected", before, after, ", ".join(conflicts))
                )
                continue
            if provenance.protection(path):
                changes.append(
                    AttributeChange(path, "unchanged", before, before, "confirmed/retained")
                )
                continue
            previous = next(
                (item for item in provenance.generated_attributes if item.path == path), None
            )
            put(path, updates[path])
            provenance = provenance.mark_generated(by_path[path])
            status = "unchanged" if before == after and previous == by_path[path] else "updated"
            changes.append(AttributeChange(path, status, before, after))
    for path, item in by_path.items():
        if item.availability != "unknown" or path in updates:
            continue
        if provenance.availability(path) != "known":
            provenance = provenance.mark_generated(item)
        changes.append(AttributeChange(path, "unknown", get(path), get(path), "no usable decision"))
    enriched = ClauseEnrichments.model_validate(
        state, context=sparse_semantic_validation_context(provenance)
    )
    result = clause.model_copy(update={"enrichments": enriched, "provenance": provenance})
    return EnrichmentMergeResult(result, tuple(changes))


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
    """Restore selected persisted knowledge through the same group-wise merge.

    Persistence is not confirmation. Conflicting explicit authorities are a hard
    error. Unattributed values stay protected; generated input cannot downgrade
    existing authority. Baseline provenance is never replaced by this operation.
    """
    known_paths = set()
    if patch.semantic is not None:
        known_paths.update(
            f"enrichments.semantic.{name}" for name in patch.semantic.model_fields_set
        )
    for name in ("context_routing", "subject_context"):
        if getattr(patch, name) is not None:
            known_paths.add(f"enrichments.{name}")
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
        value: object = patch
        for name in path.split(".")[1:]:
            value = getattr(value, name)
        return _plain(value)

    for path in protected:
        if path in incoming:
            raise ValueError("persisted generated and protected paths overlap")
        if path in confirmations and clause.provenance.protection(path) == "confirmed":
            if current_value(path) != proposed_value(path):
                raise ValueError(f"conflicting authoritative AtlasData values: {path}")
        incoming[path] = GeneratedAttribute(
            path=path,
            generator="atlasdata-roundtrip",
            method=GenerationMethod.IMPORTED,
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
        result.clause.model_copy(update={"provenance": state}),
        result.changes,
    )
