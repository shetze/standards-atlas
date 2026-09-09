"""Inspect exactly the canonical CBox values used by downstream consumers."""

from __future__ import annotations

from collections import Counter

from standards_atlas.application.context.canonical_cbox import (
    canonical_cbox_context,
    context_fingerprint,
)
from standards_atlas.application.model.cbox import CBoxReport
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseFilter,
    ClauseProvider,
)
from standards_atlas.application.semantic_qualification.context_framing import (
    frame_cbox_context,
    resolve_cbox_frame_policy,
)
from standards_atlas.application.semantic_qualification.context_projection import (
    CBOX_RENDERER_VERSION,
    render_cbox_context,
)


class CBoxReportService:
    def __init__(self, provider: ClauseProvider) -> None:
        self._provider = provider

    def build(
        self,
        *,
        document_keys: tuple[str, ...] = (),
        clause_ids: tuple[str, ...] = (),
        frame: str = "effective-context-v1",
        knowledge_domain: str = "functional-safety",
        available_only: bool = False,
    ) -> CBoxReport:
        policy = resolve_cbox_frame_policy(frame)
        available = {item.key for item in self._provider.list_documents()}
        if not available_only and set(document_keys) - available:
            raise ValueError(
                "CBox report documents are missing: "
                + ", ".join(sorted(set(document_keys) - available))
            )
        selected = sorted(set(document_keys) & available) if document_keys else sorted(available)
        # An empty explicit intersection must not fall back to all documents.
        clauses = (
            self._provider.list_clauses(filters=ClauseFilter(document_keys=tuple(selected)))
            if selected
            else ()
        )
        if set(clause_ids) - {item.id for item in clauses}:
            raise ValueError("requested clause ids are missing from the CBox report selection")
        records = []
        availability: Counter[str] = Counter()
        for clause in sorted(clauses, key=lambda item: (item.document_key, item.id)):
            if clause_ids and clause.id not in clause_ids:
                continue
            canonical = canonical_cbox_context(clause, knowledge_domain=knowledge_domain)
            framed = frame_cbox_context(canonical, policy)
            availability.update(item.availability for item in clause.enrichment_context.attributes)
            records.append(
                {
                    "document_key": clause.document_key,
                    "clause_id": clause.id,
                    "reference": clause.reference,
                    "content_hash": clause.content_hash,
                    "canonical": canonical,
                    "canonical_sha256": context_fingerprint(canonical),
                    "frame": {"id": framed.policy_id, "version": framed.policy_version},
                    "framed": dict(framed.values),
                    "framed_sha256": context_fingerprint(dict(framed.values)),
                    "rendered": render_cbox_context(framed),
                }
            )
        return CBoxReport(
            frame=frame,
            renderer_version=CBOX_RENDERER_VERSION,
            knowledge_domain=knowledge_domain,
            document_keys=tuple(selected),
            clause_count=len(records),
            availability_counts=dict(sorted(availability.items())),
            canonical_sha256=context_fingerprint(
                [
                    (
                        item["document_key"],
                        item["clause_id"],
                        item["content_hash"],
                        item["canonical_sha256"],
                    )
                    for item in records
                ]
            ),
            framed_sha256=context_fingerprint(
                [
                    (item["document_key"], item["clause_id"], item["framed_sha256"])
                    for item in records
                ]
            ),
            clauses=tuple(records),
        )
