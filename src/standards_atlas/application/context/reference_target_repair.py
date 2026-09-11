"""Allowlisted, source-verified ID completion; never a semantic routing repair."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.context.canonical_cbox import context_fingerprint
from standards_atlas.application.references.catalog import ReferenceDocumentCatalog
from standards_atlas.application.references.extractor import extract_reference_mentions
from standards_atlas.domain.model import Clause, EngineeringDocument, ReferenceRouting

EXTERNAL_TARGET_REPAIR_VERSION = "source-verified-external-single-target/v1"


class ReferenceTargetRepairEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_document_key: str = Field(min_length=1)
    source_clause_id: str = Field(min_length=1)
    reference_index: int = Field(ge=0, strict=True)
    source_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    edge_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_document_key: str = Field(min_length=1)
    target_clause_id: str = Field(min_length=1)
    target_reference: str = Field(min_length=1)


class ReferenceTargetRepairAllowlist(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    contract: Literal["context-reference-target-allowlist-v1"]
    baseline_archive: str | None = None
    entries: tuple[ReferenceTargetRepairEntry, ...]

    @model_validator(mode="after")
    def unique_edges(self) -> ReferenceTargetRepairAllowlist:
        keys = [
            (entry.source_document_key, entry.source_clause_id, entry.reference_index)
            for entry in self.entries
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("reference-target allowlist contains duplicate source edges")
        return self


def source_text_sha256(clause: Clause) -> str:
    return hashlib.sha256(clause.plain_text.encode("utf-8")).hexdigest()


def edge_sha256(edge: ReferenceRouting) -> str:
    return context_fingerprint(edge.model_dump(mode="json"))


def _verified_target(
    clause: Clause,
    edge: ReferenceRouting,
    entry: ReferenceTargetRepairEntry,
    catalog: ReferenceDocumentCatalog,
) -> str | None:
    """Return a refusal reason, or None when every independent check succeeds."""
    if edge.source_clause_id != clause.id.value:
        return "source_clause_mismatch"
    if source_text_sha256(clause) != entry.source_text_sha256:
        return "source_text_changed"
    if edge_sha256(edge) != entry.edge_sha256:
        return "edge_changed"
    if edge.target.document_key != entry.target_document_key:
        return "document_key_mismatch"
    if entry.target_document_key == catalog.document.key.value:
        return "not_an_external_target"
    if entry.target_document_key not in catalog.documents:
        return "target_document_not_loaded"
    targets = catalog.targets(edge.target.reference, clause.id.value)
    if len(targets) != 1 or targets[0].clause_id is None:
        return "not_a_unique_single_target"
    target = targets[0]
    if (target.document_key, target.clause_id, target.reference) != (
        entry.target_document_key,
        entry.target_clause_id,
        entry.target_reference,
    ):
        return "target_address_mismatch"
    source = " ".join(clause.plain_text.split())
    for evidence in edge.evidence:
        quote = " ".join(evidence.split())
        if not quote or quote not in source:
            continue
        for mention in extract_reference_mentions(evidence):
            if mention.reference is None:
                continue
            evidence_targets = catalog.targets(mention.reference, clause.id.value)
            # A fully resolved source list can prove an already explicit single
            # address. It never expands the stored edge or selects a new address.
            if all(item.clause_id is not None for item in evidence_targets) and any(
                (item.document_key, item.clause_id) == (target.document_key, target.clause_id)
                for item in evidence_targets
            ):
                return None
    return "target_not_supported_by_verbatim_source"


def complete_external_reference_targets(
    document: EngineeringDocument,
    *,
    documents: Iterable[EngineeringDocument],
    allowlist: ReferenceTargetRepairAllowlist,
) -> tuple[EngineeringDocument, list[dict]]:
    """Only fill an allowed null ID. Preserve all other values, including provenance.

    The private versioned report is the resolver proof; inference fingerprints,
    statuses and last-run ledgers must not be rewritten by an address-only repair.
    """
    catalog = ReferenceDocumentCatalog(document, documents)
    entries = {
        (entry.source_clause_id, entry.reference_index): entry
        for entry in allowlist.entries
        if entry.source_document_key == document.key.value
    }
    diagnostics: list[dict] = []
    clauses = []
    for clause in document.clauses:
        references = list(clause.context_routing.references)
        protection = clause.provenance.protection("enrichments.context_routing")
        for position, edge in enumerate(references):
            entry = entries.pop((clause.id.value, position), None)
            if entry is None:
                continue
            status = "skipped"
            if protection:
                reason = protection
                status = "protected"
            elif edge.target.clause_id is not None:
                # Even a conflicting existing ID is outside this repair's authority.
                reason = "already_addressed"
            else:
                reason = _verified_target(clause, edge, entry, catalog)
                if reason is None:
                    references[position] = edge.model_copy(
                        update={
                            "target": edge.target.model_copy(
                                update={"clause_id": entry.target_clause_id}
                            )
                        }
                    )
                    status, reason = "resolved", "allowlisted_verbatim_single_target"
            diagnostics.append(
                {
                    "kind": "reference_target_completion",
                    "source_clause_id": clause.id.value,
                    "index": position,
                    "status": status,
                    "reason": reason,
                    "source_text_sha256": source_text_sha256(clause),
                    "before_edge_sha256": edge_sha256(edge),
                    "after_edge_sha256": edge_sha256(references[position]),
                    "before": edge.target.model_dump(mode="json"),
                    "after": references[position].target.model_dump(mode="json"),
                }
            )
        if tuple(references) != clause.context_routing.references:
            clause = clause.model_copy(
                update={
                    "enrichments": clause.enrichments.model_copy(
                        update={
                            "context_routing": clause.context_routing.model_copy(
                                update={"references": tuple(references)}
                            )
                        }
                    )
                }
            )
        clauses.append(clause)
    diagnostics.extend(
        {
            "kind": "reference_target_completion",
            "source_clause_id": clause_id,
            "index": position,
            "status": "skipped",
            "reason": "source_edge_not_found",
        }
        for clause_id, position in sorted(entries)
    )
    result = document.model_copy(update={"clauses": tuple(clauses)})
    result = type(document).model_validate(result.model_dump(mode="python"))
    return result, diagnostics
