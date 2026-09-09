"""Model-free repair of canonical routing, before public projections are built."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from standards_atlas.application.context.information_routing import (
    INFORMATION_ROUTING_POLICY,
    InformationRoutingPolicy,
)
from standards_atlas.application.context.routing_normalization import (
    normalize_context_routing_targets,
)
from standards_atlas.application.references.extractor import refresh_document_references
from standards_atlas.application.references.resolution import DocumentReferenceIndex
from standards_atlas.domain.model import EngineeringDocument


@dataclass(frozen=True)
class ContextRoutingRepair:
    document: EngineeringDocument
    report: dict


def repair_context_routing(
    document: EngineeringDocument, *, documents: Iterable[EngineeringDocument] = ()
) -> ContextRoutingRepair:
    """Return a repaired copy and diagnostics; never overwrite reviewed attributes."""
    refreshed = refresh_document_references(document)
    index = DocumentReferenceIndex(refreshed)
    information_policy = InformationRoutingPolicy(refreshed, documents)
    diagnostics: list[dict] = []
    clauses = []
    for clause in refreshed.clauses:
        routing = clause.context_routing
        protection = clause.provenance.protection("enrichments.context_routing")
        if protection and (routing.references or routing.scopes):
            diagnostics.append(
                {
                    "kind": "protected",
                    "source_clause_id": clause.id.value,
                    "status": "protected",
                    "reason": protection,
                }
            )
        elif routing.references or routing.scopes:
            normalized = normalize_context_routing_targets(
                information_policy.normalize(routing, diagnostics=diagnostics),
                refreshed,
                index=index,
                diagnostics=diagnostics,
            )
            if normalized != routing:
                clause = clause.model_copy(
                    update={
                        "enrichments": clause.enrichments.model_copy(
                            update={"context_routing": normalized}
                        )
                    }
                )
        clauses.append(clause)
    result = refreshed.model_copy(update={"clauses": tuple(clauses)})
    # Validate copied values as well; model_copy intentionally does not validate.
    result = type(document).model_validate(result.model_dump(mode="python"))
    report = {
        "contract": "context-routing-repair-v1",
        "resolver": "document-coordinates-v4",
        "semantic_policy": INFORMATION_ROUTING_POLICY,
        "document_key": document.key.value,
        "clauses_changed": sum(
            a != b for a, b in zip(document.clauses, result.clauses, strict=True)
        ),
        "routing_clauses_changed": sum(
            a.context_routing != b.context_routing
            for a, b in zip(document.clauses, result.clauses, strict=True)
        ),
        "baseline_clauses_refreshed": sum(
            a.baseline != b.baseline for a, b in zip(document.clauses, result.clauses, strict=True)
        ),
        "scopes_before": sum(len(clause.context_routing.scopes) for clause in document.clauses),
        "scopes_after": sum(len(clause.context_routing.scopes) for clause in result.clauses),
        "informational_scopes_reclassified": sum(
            item["kind"] == "scope_semantics" and item["status"] == "corrected"
            for item in diagnostics
        ),
        "reference_roles_corrected": sum(item["kind"] == "reference_role" for item in diagnostics),
        "unresolved_references_after": sum(
            edge.target.clause_id is None
            for clause in result.clauses
            for edge in clause.context_routing.references
        ),
        "references_before": sum(
            len(clause.context_routing.references) for clause in document.clauses
        ),
        "references_after": sum(
            len(clause.context_routing.references) for clause in result.clauses
        ),
        "requires_review": sum(
            item["status"] not in {"resolved", "external", "protected", "corrected"}
            for item in diagnostics
        ),
        "routing_clauses_without_source_text": sum(
            bool(clause.context_routing.references or clause.context_routing.scopes)
            and not clause.plain_text.strip()
            for clause in document.clauses
        ),
        "protected_clauses": sum(item["status"] == "protected" for item in diagnostics),
        "diagnostics": diagnostics,
    }
    return ContextRoutingRepair(result, report)
