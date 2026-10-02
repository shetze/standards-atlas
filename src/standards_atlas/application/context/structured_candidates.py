"""Deterministic structural context candidate discovery for AP02.

Candidate discovery is deliberately weaker than semantic reach.  Hierarchy, document order and
resolved references make a source *reachable* for later selection; none of those facts alone makes
foreign source content part of the target clause's meaning.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.context.source_surfaces import (
    SourceSurfaceAvailability,
    SourceSurfaceRef,
    SourceSurfaceResolution,
    SourceSurfaceResolver,
    clause_has_heading_source_surface,
    source_document_binding,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseType,
    EngineeringDocument,
    EvidenceSourceKind,
    ReferenceResolutionStatus,
    RelationScope,
)

STRUCTURED_CONTEXT_CANDIDATE_CONTRACT = "structured-context-candidates-v1"


class ContextCandidateReason(StrEnum):
    """Structural reason why a source surface is reachable for the target clause."""

    TARGET_BODY = "target_body"
    TARGET_HEADING = "target_heading"
    ANCESTOR_BODY = "ancestor_body"
    ANCESTOR_HEADING = "ancestor_heading"
    SEQUENCE_PREVIOUS = "sequence_previous"
    SEQUENCE_NEXT = "sequence_next"
    FIRST_LEAF_CANDIDATE = "first_leaf_candidate"
    DIRECT_INTERNAL_REFERENCE = "direct_internal_reference"
    REVERSE_INTERNAL_REFERENCE = "reverse_internal_reference"
    EXPLICIT_EXTERNAL_REFERENCE = "explicit_external_reference"


class ContextPathKind(StrEnum):
    SELF = "self"
    ANCESTOR = "ancestor"
    SEQUENCE = "sequence"
    DIRECT_REFERENCE = "direct_reference"
    REVERSE_REFERENCE = "reverse_reference"
    EXTERNAL_REFERENCE = "external_reference"


class ContextDiagnosticCode(StrEnum):
    MISSING_PARENT = "missing_parent"
    ANCESTOR_CYCLE = "ancestor_cycle"
    PARENT_AFTER_CHILD = "parent_after_child"
    UNRESOLVED_REFERENCE = "unresolved_reference"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"
    EXTERNAL_REFERENCE_UNBOUND = "external_reference_unbound"
    EXTERNAL_BINDING_UNVERSIONED = "external_binding_unversioned"
    SOURCE_UNAVAILABLE = "source_unavailable"


class ContextStructuralNode(BaseModel):
    """One ancestor in the real parent chain, including textless grouping nodes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    parent_id: str | None = None
    document_position: int = Field(ge=0)
    heading_present: bool
    body_present: bool


class ContextCandidatePath(BaseModel):
    """Explainable structural/reference path that made a candidate reachable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ContextPathKind
    from_clause_id: str = Field(min_length=1)
    to_clause_id: str = Field(min_length=1)
    via_clause_ids: tuple[str, ...] = ()
    direction: Literal["backward", "forward", "same"] | None = None
    distance: int | None = Field(default=None, ge=0)
    reference_text: str | None = None


class ContextCandidate(BaseModel):
    """One source surface plus every structural reason for considering it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(min_length=1)
    source_ref: SourceSurfaceRef
    resolution: SourceSurfaceResolution
    reasons: tuple[ContextCandidateReason, ...] = Field(min_length=1)
    paths: tuple[ContextCandidatePath, ...] = Field(min_length=1)
    reach_status: Literal["target", "unconfirmed"]


class ContextCandidateDiagnostic(BaseModel):
    """Visible structural/reference boundary; never a hidden fallback."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ContextDiagnosticCode
    message: str = Field(min_length=1)
    source_clause_id: str | None = None
    target_clause_id: str | None = None
    target_document_key: str | None = None
    target_reference: str | None = None


class StructuredContextCandidates(BaseModel):
    """Deterministic candidate inventory before budget or semantic use decisions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: Literal["structured-context-candidates-v1"] = STRUCTURED_CONTEXT_CANDIDATE_CONTRACT
    document_key: str = Field(min_length=1)
    document_revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_clause_id: str = Field(min_length=1)
    target_reference: str = Field(min_length=1)
    ancestor_path: tuple[ContextStructuralNode, ...] = ()
    sequence_clause_ids: tuple[str, ...] = ()
    candidates: tuple[ContextCandidate, ...] = ()
    diagnostics: tuple[ContextCandidateDiagnostic, ...] = ()


class _ReferenceEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_clause_id: str
    target_document_key: str | None
    target_clause_id: str | None
    target_reference: str | None
    reference_text: str | None
    external: bool


def build_structured_context_candidates(
    document: EngineeringDocument,
    target: Clause,
    *,
    resolver: SourceSurfaceResolver | None = None,
    external_source_refs: tuple[SourceSurfaceRef, ...] = (),
) -> StructuredContextCandidates:
    """Build hierarchy, two-sided sequence and reference candidates for ``target``.

    The current document itself is an explicit source binding.  External content is different:
    even if the resolver happens to contain another document, an external candidate is materialized
    only when the caller supplies an exact, revision-bound ``external_source_refs`` entry.
    """

    binding = source_document_binding(document)
    source_resolver = resolver or SourceSurfaceResolver((document,))
    positions = {clause.id.value: index for index, clause in enumerate(document.clauses)}
    by_id = {clause.id.value: clause for clause in document.clauses}
    canonical_target = by_id.get(target.id.value)
    if canonical_target is None:
        raise ValueError(
            f"target clause {target.id.value!r} is not in document {document.key.value!r}"
        )

    diagnostics: list[ContextCandidateDiagnostic] = []
    ancestors = _ancestor_path(canonical_target, by_id, positions, diagnostics)
    sequence = _sequence_group(canonical_target, document.clauses, by_id)
    sequence_ids = tuple(item.id.value for item in sequence)
    target_position = positions[canonical_target.id.value]

    candidates: dict[str, ContextCandidate] = {}

    _add_clause_surfaces(
        candidates,
        source_resolver,
        document,
        canonical_target,
        reasons=(ContextCandidateReason.TARGET_BODY, ContextCandidateReason.TARGET_HEADING),
        path=ContextCandidatePath(
            kind=ContextPathKind.SELF,
            from_clause_id=canonical_target.id.value,
            to_clause_id=canonical_target.id.value,
            direction="same",
            distance=0,
        ),
        target=True,
        diagnostics=diagnostics,
        add_body=True,
        add_heading=True,
    )

    for depth, ancestor in enumerate(ancestors, start=1):
        parent_clause = by_id[ancestor.clause_id]
        _add_clause_surfaces(
            candidates,
            source_resolver,
            document,
            parent_clause,
            reasons=(
                ContextCandidateReason.ANCESTOR_BODY,
                ContextCandidateReason.ANCESTOR_HEADING,
            ),
            path=ContextCandidatePath(
                kind=ContextPathKind.ANCESTOR,
                from_clause_id=parent_clause.id.value,
                to_clause_id=canonical_target.id.value,
                via_clause_ids=tuple(item.clause_id for item in ancestors[: depth - 1]),
                direction="backward",
                distance=depth,
            ),
            target=False,
            diagnostics=diagnostics,
            add_body=True,
            add_heading=True,
        )

    first_leaf_id = sequence_ids[0] if sequence_ids else None
    for sibling in sequence:
        if sibling.id == canonical_target.id:
            continue
        sibling_position = positions[sibling.id.value]
        delta = sibling_position - target_position
        reason = (
            ContextCandidateReason.SEQUENCE_NEXT
            if delta > 0
            else ContextCandidateReason.SEQUENCE_PREVIOUS
        )
        extra_reasons = (
            (ContextCandidateReason.FIRST_LEAF_CANDIDATE,)
            if sibling.id.value == first_leaf_id
            else ()
        )
        _add_clause_surfaces(
            candidates,
            source_resolver,
            document,
            sibling,
            reasons=(reason, *extra_reasons),
            path=ContextCandidatePath(
                kind=ContextPathKind.SEQUENCE,
                from_clause_id=sibling.id.value,
                to_clause_id=canonical_target.id.value,
                via_clause_ids=(canonical_target.parent_id.value,)
                if canonical_target.parent_id is not None
                else (),
                direction="forward" if delta > 0 else "backward",
                distance=abs(
                    sequence_ids.index(sibling.id.value)
                    - sequence_ids.index(canonical_target.id.value)
                ),
            ),
            target=False,
            diagnostics=diagnostics,
            add_body=True,
            add_heading=True,
        )

    if canonical_target.id.value == first_leaf_id:
        _merge_reason_into_clause_candidates(
            candidates,
            canonical_target.id.value,
            ContextCandidateReason.FIRST_LEAF_CANDIDATE,
        )

    edges_by_source = {
        clause.id.value: _reference_edges(clause, document.key.value) for clause in document.clauses
    }
    for edge in edges_by_source[canonical_target.id.value]:
        if edge.external:
            _add_external_edge_candidates(
                candidates,
                diagnostics,
                source_resolver,
                edge,
                canonical_target,
                external_source_refs,
            )
            continue
        if edge.target_clause_id is None or edge.target_clause_id not in by_id:
            continue
        referenced = by_id[edge.target_clause_id]
        _add_clause_surfaces(
            candidates,
            source_resolver,
            document,
            referenced,
            reasons=(ContextCandidateReason.DIRECT_INTERNAL_REFERENCE,),
            path=ContextCandidatePath(
                kind=ContextPathKind.DIRECT_REFERENCE,
                from_clause_id=canonical_target.id.value,
                to_clause_id=referenced.id.value,
                direction=_document_direction(target_position, positions[referenced.id.value]),
                distance=abs(positions[referenced.id.value] - target_position),
                reference_text=edge.reference_text,
            ),
            target=False,
            diagnostics=diagnostics,
            add_body=True,
            add_heading=True,
        )

    target_linked_sequence_ids = {
        edge.target_clause_id
        for edge in edges_by_source[canonical_target.id.value]
        if not edge.external
        and edge.target_clause_id is not None
        and edge.target_clause_id in sequence_ids
    }
    reverse_targets = {canonical_target.id.value, *target_linked_sequence_ids}
    for source in document.clauses:
        if source.id == canonical_target.id:
            continue
        for edge in edges_by_source[source.id.value]:
            if edge.external or edge.target_clause_id not in reverse_targets:
                continue
            _add_clause_surfaces(
                candidates,
                source_resolver,
                document,
                source,
                reasons=(ContextCandidateReason.REVERSE_INTERNAL_REFERENCE,),
                path=ContextCandidatePath(
                    kind=ContextPathKind.REVERSE_REFERENCE,
                    from_clause_id=source.id.value,
                    to_clause_id=edge.target_clause_id or canonical_target.id.value,
                    direction=_document_direction(target_position, positions[source.id.value]),
                    distance=abs(positions[source.id.value] - target_position),
                    reference_text=edge.reference_text,
                ),
                target=False,
                diagnostics=diagnostics,
                add_body=True,
                add_heading=True,
            )

    diagnostics.extend(_reference_diagnostics(canonical_target))
    return StructuredContextCandidates(
        document_key=document.key.value,
        document_revision=binding.source_revision,
        target_clause_id=canonical_target.id.value,
        target_reference=canonical_target.reference.clause,
        ancestor_path=tuple(ancestors),
        sequence_clause_ids=sequence_ids,
        candidates=tuple(candidates.values()),
        diagnostics=tuple(_dedupe_diagnostics(diagnostics)),
    )


def _ancestor_path(
    target: Clause,
    by_id: dict[str, Clause],
    positions: dict[str, int],
    diagnostics: list[ContextCandidateDiagnostic],
) -> list[ContextStructuralNode]:
    result: list[ContextStructuralNode] = []
    seen = {target.id.value}
    child = target
    parent_id = target.parent_id.value if target.parent_id is not None else None
    while parent_id is not None:
        if parent_id in seen:
            diagnostics.append(
                ContextCandidateDiagnostic(
                    code=ContextDiagnosticCode.ANCESTOR_CYCLE,
                    message="ancestor traversal stopped at a repeated clause id",
                    source_clause_id=child.id.value,
                    target_clause_id=parent_id,
                )
            )
            break
        seen.add(parent_id)
        parent = by_id.get(parent_id)
        if parent is None:
            diagnostics.append(
                ContextCandidateDiagnostic(
                    code=ContextDiagnosticCode.MISSING_PARENT,
                    message="ancestor traversal stopped because the declared parent is absent",
                    source_clause_id=child.id.value,
                    target_clause_id=parent_id,
                )
            )
            break
        parent_position = positions[parent.id.value]
        if parent_position > positions[child.id.value]:
            diagnostics.append(
                ContextCandidateDiagnostic(
                    code=ContextDiagnosticCode.PARENT_AFTER_CHILD,
                    message="declared parent occurs after its child in canonical document order",
                    source_clause_id=child.id.value,
                    target_clause_id=parent.id.value,
                )
            )
        result.append(
            ContextStructuralNode(
                clause_id=parent.id.value,
                reference=parent.reference.clause,
                parent_id=parent.parent_id.value if parent.parent_id is not None else None,
                document_position=parent_position,
                heading_present=clause_has_heading_source_surface(parent),
                body_present=bool(parent.plain_text),
            )
        )
        child = parent
        parent_id = parent.parent_id.value if parent.parent_id is not None else None
    return result


def _sequence_group(
    target: Clause,
    clauses: tuple[Clause, ...],
    by_id: dict[str, Clause],
) -> tuple[Clause, ...]:
    if target.parent_id is None:
        return (target,)
    parent_id = target.parent_id.value
    if parent_id not in by_id:
        return (target,)
    parents = {
        item.parent_id.value
        for item in clauses
        if item.parent_id is not None and item.parent_id.value in by_id
    }
    if target.id.value in parents:
        return (target,)
    return tuple(
        item
        for item in clauses
        if item.parent_id is not None
        and item.parent_id.value == parent_id
        and item.id.value not in parents
        and item.clause_type not in {ClauseType.TOC, ClauseType.TABLE}
    )


def _add_clause_surfaces(
    candidates: dict[str, ContextCandidate],
    resolver: SourceSurfaceResolver,
    document: EngineeringDocument,
    clause: Clause,
    *,
    reasons: tuple[ContextCandidateReason, ...],
    path: ContextCandidatePath,
    target: bool,
    diagnostics: list[ContextCandidateDiagnostic],
    add_body: bool,
    add_heading: bool,
) -> None:
    revision = source_document_binding(document).source_revision
    if add_body:
        _add_candidate(
            candidates,
            resolver,
            SourceSurfaceRef(
                document_key=document.key.value,
                document_revision=revision,
                clause_id=clause.id.value,
                source_kind=EvidenceSourceKind.BODY,
            ),
            tuple(
                reason
                for reason in reasons
                if reason
                not in {
                    ContextCandidateReason.TARGET_HEADING,
                    ContextCandidateReason.ANCESTOR_HEADING,
                }
            ),
            path,
            target=target,
            diagnostics=diagnostics,
        )
    if add_heading and clause_has_heading_source_surface(clause):
        _add_candidate(
            candidates,
            resolver,
            SourceSurfaceRef(
                document_key=document.key.value,
                document_revision=revision,
                clause_id=clause.id.value,
                source_kind=EvidenceSourceKind.HEADING,
            ),
            tuple(
                reason
                for reason in reasons
                if reason
                not in {
                    ContextCandidateReason.TARGET_BODY,
                    ContextCandidateReason.ANCESTOR_BODY,
                }
            ),
            path,
            target=target,
            diagnostics=diagnostics,
        )


def _add_candidate(
    candidates: dict[str, ContextCandidate],
    resolver: SourceSurfaceResolver,
    source_ref: SourceSurfaceRef,
    reasons: tuple[ContextCandidateReason, ...],
    path: ContextCandidatePath,
    *,
    target: bool,
    diagnostics: list[ContextCandidateDiagnostic],
) -> None:
    if not reasons:
        return
    candidate_id = _candidate_id(source_ref)
    existing = candidates.get(candidate_id)
    if existing is not None:
        candidates[candidate_id] = existing.model_copy(
            update={
                "reasons": _ordered_unique((*existing.reasons, *reasons)),
                "paths": _ordered_unique((*existing.paths, path)),
                "reach_status": (
                    "target" if target or existing.reach_status == "target" else "unconfirmed"
                ),
            }
        )
        return
    resolution = resolver.resolve(source_ref)
    if resolution.availability is not SourceSurfaceAvailability.AVAILABLE:
        diagnostics.append(
            ContextCandidateDiagnostic(
                code=ContextDiagnosticCode.SOURCE_UNAVAILABLE,
                message=f"candidate source surface is {resolution.availability.value}",
                source_clause_id=source_ref.clause_id,
                target_document_key=source_ref.document_key,
            )
        )
    candidates[candidate_id] = ContextCandidate(
        candidate_id=candidate_id,
        source_ref=source_ref,
        resolution=resolution,
        reasons=_ordered_unique(reasons),
        paths=(path,),
        reach_status="target" if target else "unconfirmed",
    )


def _merge_reason_into_clause_candidates(
    candidates: dict[str, ContextCandidate], clause_id: str, reason: ContextCandidateReason
) -> None:
    for key, candidate in tuple(candidates.items()):
        if candidate.source_ref.clause_id != clause_id:
            continue
        candidates[key] = candidate.model_copy(
            update={"reasons": _ordered_unique((*candidate.reasons, reason))}
        )


def _reference_edges(clause: Clause, current_document_key: str) -> tuple[_ReferenceEdge, ...]:
    edges: list[_ReferenceEdge] = []
    for mention in clause.reference_mentions:
        for target in mention.targets:
            target_document = target.document_key
            edges.append(
                _ReferenceEdge(
                    source_clause_id=clause.id.value,
                    target_document_key=target_document,
                    target_clause_id=target.clause_id,
                    target_reference=target.reference,
                    reference_text=mention.surface_text,
                    external=target_document not in {None, current_document_key},
                )
            )
    for relation in clause.reference_relations:
        edges.append(
            _ReferenceEdge(
                source_clause_id=clause.id.value,
                target_document_key=relation.target_document_key,
                target_clause_id=relation.target_clause_id,
                target_reference=relation.target_reference,
                reference_text=relation.display_text or relation.target_reference,
                external=(
                    relation.scope is RelationScope.EXTERNAL
                    or relation.target_document_key not in {None, current_document_key}
                ),
            )
        )
    unique: dict[tuple[object, ...], _ReferenceEdge] = {}
    for edge in edges:
        key = (
            edge.source_clause_id,
            edge.target_document_key,
            edge.target_clause_id,
            edge.target_reference,
            edge.reference_text,
            edge.external,
        )
        unique[key] = edge
    return tuple(unique.values())


def _reference_diagnostics(
    clause: Clause,
) -> tuple[ContextCandidateDiagnostic, ...]:
    diagnostics: list[ContextCandidateDiagnostic] = []
    for mention in clause.reference_mentions:
        if mention.status in {
            ReferenceResolutionStatus.UNRESOLVED,
            ReferenceResolutionStatus.PARTIALLY_RESOLVED,
            ReferenceResolutionStatus.DEFERRED,
        }:
            diagnostics.append(
                ContextCandidateDiagnostic(
                    code=ContextDiagnosticCode.UNRESOLVED_REFERENCE,
                    message=f"reference mention remains {mention.status.value}",
                    source_clause_id=clause.id.value,
                    target_reference=(
                        mention.reference or mention.range_start or mention.surface_text
                    ),
                )
            )
        elif mention.status is ReferenceResolutionStatus.AMBIGUOUS:
            diagnostics.append(
                ContextCandidateDiagnostic(
                    code=ContextDiagnosticCode.AMBIGUOUS_REFERENCE,
                    message="reference mention has multiple possible targets",
                    source_clause_id=clause.id.value,
                    target_reference=(
                        mention.reference or mention.range_start or mention.surface_text
                    ),
                )
            )
    return tuple(diagnostics)


def _add_external_edge_candidates(
    candidates: dict[str, ContextCandidate],
    diagnostics: list[ContextCandidateDiagnostic],
    resolver: SourceSurfaceResolver,
    edge: _ReferenceEdge,
    target: Clause,
    external_source_refs: tuple[SourceSurfaceRef, ...],
) -> None:
    matching = tuple(
        source_ref
        for source_ref in external_source_refs
        if source_ref.document_key == edge.target_document_key
        and (edge.target_clause_id is None or source_ref.clause_id == edge.target_clause_id)
    )
    if not matching:
        diagnostics.append(
            ContextCandidateDiagnostic(
                code=ContextDiagnosticCode.EXTERNAL_REFERENCE_UNBOUND,
                message=(
                    "external reference is identified but no explicit source binding was supplied"
                ),
                source_clause_id=edge.source_clause_id,
                target_clause_id=edge.target_clause_id,
                target_document_key=edge.target_document_key,
                target_reference=edge.target_reference,
            )
        )
        return
    for source_ref in matching:
        if source_ref.document_revision is None:
            diagnostics.append(
                ContextCandidateDiagnostic(
                    code=ContextDiagnosticCode.EXTERNAL_BINDING_UNVERSIONED,
                    message=(
                        "external source binding is rejected because document_revision is absent"
                    ),
                    source_clause_id=edge.source_clause_id,
                    target_clause_id=source_ref.clause_id,
                    target_document_key=source_ref.document_key,
                    target_reference=edge.target_reference,
                )
            )
            continue
        _add_candidate(
            candidates,
            resolver,
            source_ref,
            (ContextCandidateReason.EXPLICIT_EXTERNAL_REFERENCE,),
            ContextCandidatePath(
                kind=ContextPathKind.EXTERNAL_REFERENCE,
                from_clause_id=target.id.value,
                to_clause_id=source_ref.clause_id,
                reference_text=edge.reference_text,
            ),
            target=False,
            diagnostics=diagnostics,
        )


def _document_direction(
    source_position: int, target_position: int
) -> Literal["backward", "forward", "same"]:
    if target_position > source_position:
        return "forward"
    if target_position < source_position:
        return "backward"
    return "same"


def _candidate_id(source_ref: SourceSurfaceRef) -> str:
    kind = (
        source_ref.source_kind.value
        if source_ref.source_kind is not None
        else source_ref.media_kind.value
    )
    block = source_ref.block_id or "-"
    revision = source_ref.document_revision or "unbound"
    return f"{source_ref.document_key}:{revision}:{source_ref.clause_id}:{kind}:{block}"


def _ordered_unique[T](values: tuple[T, ...]) -> tuple[T, ...]:
    unique: list[T] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return tuple(unique)


def _dedupe_diagnostics(
    values: list[ContextCandidateDiagnostic],
) -> tuple[ContextCandidateDiagnostic, ...]:
    unique: dict[tuple[object, ...], ContextCandidateDiagnostic] = {}
    for value in values:
        key = (
            value.code,
            value.message,
            value.source_clause_id,
            value.target_clause_id,
            value.target_document_key,
            value.target_reference,
        )
        unique[key] = value
    return tuple(unique.values())
