"""Model-free repair of canonical routing, before public projections are built."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from standards_atlas.application.context.canonical_cbox import context_fingerprint
from standards_atlas.application.context.information_routing import (
    INFORMATION_ROUTING_POLICY,
    InformationRoutingPolicy,
)
from standards_atlas.application.context.reference_target_repair import (
    EXTERNAL_TARGET_REPAIR_VERSION,
    ReferenceTargetRepairAllowlist,
    complete_external_reference_targets,
)
from standards_atlas.application.context.routing_normalization import (
    normalize_context_routing_targets,
)
from standards_atlas.application.references.diagnostics import TARGET_DIAGNOSTICS_CONTRACT
from standards_atlas.application.references.extractor import refresh_document_references
from standards_atlas.application.references.resolution import DocumentReferenceIndex
from standards_atlas.application.services.context_enrichment_service import (
    _unresolved_reference_targets,
    _unresolved_scope_targets,
)
from standards_atlas.domain.model import EngineeringDocument


@dataclass(frozen=True)
class ContextRoutingRepair:
    document: EngineeringDocument
    report: dict


def repair_context_routing(
    document: EngineeringDocument,
    *,
    documents: Iterable[EngineeringDocument] = (),
    reference_targets_only: bool = False,
    allowlist: ReferenceTargetRepairAllowlist | None = None,
) -> ContextRoutingRepair:
    """Return a repaired copy and diagnostics; never overwrite reviewed attributes."""
    documents = tuple(documents)
    if reference_targets_only:
        if allowlist is None:
            raise ValueError("--reference-targets-only requires --allowlist")
        return _complete_reference_targets(document, documents, allowlist)
    if allowlist is not None:
        raise ValueError("--allowlist requires --reference-targets-only")
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
    report.update(_target_diagnostics(result, documents))
    return ContextRoutingRepair(result, report)


def _target_diagnostics(
    document: EngineeringDocument, documents: tuple[EngineeringDocument, ...]
) -> dict[str, object]:
    scopes = _unresolved_scope_targets(document, documents=documents)
    references = _unresolved_reference_targets(document, documents=documents)
    return {
        "target_diagnostics_contract": TARGET_DIAGNOSTICS_CONTRACT,
        "unresolved_scope_targets": scopes,
        "unresolved_reference_targets": references,
        "unresolved_scope_reasons": dict(sorted(Counter(x["reason"] for x in scopes).items())),
        "unresolved_reference_reasons": dict(
            sorted(Counter(x["reason"] for x in references).items())
        ),
    }


def _complete_reference_targets(
    document: EngineeringDocument,
    documents: tuple[EngineeringDocument, ...],
    allowlist: ReferenceTargetRepairAllowlist,
) -> ContextRoutingRepair:
    result, diagnostics = complete_external_reference_targets(
        document, documents=documents, allowlist=allowlist
    )
    changed = sum(a != b for a, b in zip(document.clauses, result.clauses, strict=True))
    references = sum(len(c.context_routing.references) for c in document.clauses)
    scopes = sum(len(c.context_routing.scopes) for c in document.clauses)
    report = {
        "contract": "context-routing-reference-target-repair-v1",
        "resolver": EXTERNAL_TARGET_REPAIR_VERSION,
        "mode": "reference_targets_only",
        "document_key": document.key.value,
        "allowlist_sha256": context_fingerprint(allowlist.model_dump(mode="json")),
        "baseline_archive": allowlist.baseline_archive,
        "clauses_changed": changed,
        "routing_clauses_changed": changed,
        "baseline_clauses_refreshed": 0,
        "scopes_before": scopes,
        "scopes_after": scopes,
        "references_before": references,
        "references_after": references,
        "reference_roles_corrected": 0,
        "informational_scopes_reclassified": 0,
        "reference_ids_completed": sum(x["status"] == "resolved" for x in diagnostics),
        "unresolved_references_after": sum(
            edge.target.clause_id is None
            for clause in result.clauses
            for edge in clause.context_routing.references
        ),
        "requires_review": sum(
            x["status"] == "skipped" and x["reason"] != "already_addressed" for x in diagnostics
        ),
        "protected_clauses": len(
            {x["source_clause_id"] for x in diagnostics if x["status"] == "protected"}
        ),
        "diagnostics": diagnostics,
        **_target_diagnostics(result, documents),
    }
    return ContextRoutingRepair(result, report)
