"""Resolve routing coordinates before persistence; recover only grounded evidence."""

from __future__ import annotations

from standards_atlas.application.references.extractor import extract_reference_mentions
from standards_atlas.application.references.resolution import (
    DocumentReferenceIndex,
    ReferenceResolution,
    canonical_reference,
    reference_key,
)
from standards_atlas.domain.model import ContextRouting, EngineeringDocument, ReferenceRouting
from standards_atlas.domain.model.reference_mention import ReferenceTarget


def _text_key(text: str) -> str:
    # Whitespace-only normalization: paraphrases are not verified source evidence.
    return " ".join(text.split())


def _evidence_groups(
    edge: ReferenceRouting,
    index: DocumentReferenceIndex,
    *,
    grounded_only: bool = True,
) -> tuple[tuple[str, ReferenceResolution], ...]:
    source = index.clauses.get(edge.source_clause_id)
    source_text = _text_key(source.plain_text) if source else ""
    if grounded_only and not source_text:
        return ()
    groups: dict[str, tuple[str, ReferenceResolution]] = {}
    for evidence in edge.evidence:
        if not evidence.strip() or (grounded_only and _text_key(evidence) not in source_text):
            continue
        for mention in extract_reference_mentions(evidence):
            text = mention.reference or (
                mention.surface_text if mention.direction_hint == "self" else None
            )
            if text is not None:
                groups[reference_key(text)] = (
                    text,
                    index.resolve_group(text, edge.source_clause_id),
                )
    return tuple(groups.values())


def _reference_targets(
    edge: ReferenceRouting,
    index: DocumentReferenceIndex,
) -> tuple[tuple[ReferenceTarget, ...], str, str]:
    target = edge.target
    if target.document_key not in (None, index.document_key):
        return (target,), "external", "external_document_not_loaded"
    text = target.reference
    resolution = index.resolve_group(text, edge.source_clause_id)
    reason = "exact_document_coordinates"
    groups = _evidence_groups(edge, index)
    direct_ids = {clause.id.value for clause in resolution.targets}
    supported = any(
        (
            resolution.status == "resolved"
            and direct_ids
            and direct_ids <= {clause.id.value for clause in result.targets}
        )
        or reference_key(text) == reference_key(surface)
        for surface, result in groups
    )
    if not groups:
        unverified = _evidence_groups(edge, index, grounded_only=False)
        if unverified and not any(
            direct_ids
            and direct_ids <= {clause.id.value for clause in result.targets}
            or reference_key(text) == reference_key(surface)
            for surface, result in unverified
        ):
            return (
                (target.model_copy(update={"clause_id": None, "title": None}),),
                "unverified",
                "conflicting_evidence_not_grounded_in_source",
            )
    if groups and not supported:
        if len(groups) == 1:
            text, resolution = groups[0]
            reason = "recovered_from_verbatim_source_evidence"
        else:
            # Multiple citations in an evidence sentence do not prove which one
            # carries this edge's role. Do not select one or expand all blindly.
            resolution = ReferenceResolution(status="ambiguous")
            reason = "conflicting_evidence_requires_review"
    if resolution.status != "resolved":
        return (
            (target.model_copy(update={"clause_id": None, "reference": text, "title": None}),),
            resolution.status,
            reason,
        )
    return (
        tuple(
            ReferenceTarget(
                document_key=index.document_key,
                clause_id=clause.id.value,
                reference=canonical_reference(clause),
                title=(
                    clause.heading
                    if target.title is not None and target.clause_id != clause.id.value
                    else target.title
                ),
            )
            for clause in resolution.targets
        ),
        "resolved",
        reason,
    )


def normalize_context_routing_targets(
    routing: ContextRouting,
    document: EngineeringDocument,
    *,
    diagnostics: list[dict] | None = None,
    index: DocumentReferenceIndex | None = None,
) -> ContextRouting:
    """Validate both explicit reference edges and explicitly addressed scope reaches.

    A provider ID is never a substitute for an exact textual coordinate. Compound
    citations expand only if every target resolves uniquely. Already overwritten
    reference text can be recovered from one unambiguous, verbatim source-evidence
    citation; unrelated citations are not assigned a role by guessing. Scope
    evidence is *not* used as a target (a condition may cite a different region).
    Deterministically supplied scope edges take precedence over stale display text.
    """
    if not routing.scopes and not routing.references:
        return routing
    index = index or DocumentReferenceIndex(document)
    references = []
    for position, edge in enumerate(routing.references):
        targets, status, reason = _reference_targets(edge, index)
        references.extend(edge.model_copy(update={"target": target}) for target in targets)
        if diagnostics is not None and (
            targets != (edge.target,) or status not in {"resolved", "external"}
        ):
            diagnostics.append(
                {
                    "kind": "reference",
                    "source_clause_id": edge.source_clause_id,
                    "index": position,
                    "status": status,
                    "reason": reason,
                    "before": edge.target.model_dump(mode="json"),
                    "after": [target.model_dump(mode="json") for target in targets],
                }
            )

    scopes = []
    for position, scope in enumerate(routing.scopes):
        source = index.clauses.get(scope.source_clause_id)
        structural = source.structural_context if source else None
        structural_ids = (
            {
                edge.target_clause_id
                for edge in structural.scopes
                if edge.status == "resolved" and edge.target_clause_id is not None
            }
            if structural
            else set()
        )
        reaches = []
        for reach_position, reach in enumerate(scope.reaches):
            if reach.kind.value in {"document", "part"} or reach.document_key not in (
                None,
                index.document_key,
            ):
                reaches.append(reach)
                continue
            clause = index.clauses.get(reach.clause_id)
            reason = "exact_document_coordinates"
            explicit = bool(reach.reference and index.coordinates(reach.reference))
            if clause and (reach.clause_id in structural_ids or not explicit):
                result = ReferenceResolution((clause,), "resolved")
                reason = "deterministic_scope_edge" if explicit else "interpreted_scope_id"
            else:
                result = index.resolve_group(reach.reference or "", scope.source_clause_id)
            if result.status == "resolved":
                normalized = tuple(
                    reach.model_copy(
                        update={
                            "document_key": index.document_key,
                            "clause_id": target.id.value,
                            "reference": canonical_reference(target),
                        }
                    )
                    for target in result.targets
                )
            else:
                normalized = (
                    reach.model_copy(
                        update={
                            "clause_id": None,
                            "reference": reach.reference or reach.clause_id,
                        }
                    ),
                )
            reaches.extend(normalized)
            if diagnostics is not None and (normalized != (reach,) or result.status != "resolved"):
                diagnostics.append(
                    {
                        "kind": "scope",
                        "source_clause_id": scope.source_clause_id,
                        "index": position,
                        "reach_index": reach_position,
                        "status": result.status,
                        "reason": reason,
                        "before": reach.model_dump(mode="json"),
                        "after": [item.model_dump(mode="json") for item in normalized],
                    }
                )
        scopes.append(scope.model_copy(update={"reaches": tuple(reaches)}))
    return routing.model_copy(update={"scopes": tuple(scopes), "references": tuple(references)})
