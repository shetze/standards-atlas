"""Explicit, LLM-free materialization of selected results in existing documents."""

from __future__ import annotations

from collections import Counter, defaultdict

from standards_atlas.application.context.source_structure import project_source_structure
from standards_atlas.application.model.knowledge_adoption import (
    ClauseAdoptionResult,
    KnowledgeAdoptionBatch,
    KnowledgeAdoptionReport,
)
from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.domain.model import DocumentKey, EngineeringDocument
from standards_atlas.domain.model.enrichment_patch import merge_generated_enrichments


class KnowledgeAdoptionService:
    """Validate the entire target selection before any repository write.

    Qualification stays read-only. This service alone accepts candidates into
    the canonical state, never as authoritative confirmations. Documents and
    clauses outside the explicitly selected subset are not replaced.
    """

    def __init__(self, *, documents: EngineeringDocumentRepository) -> None:
        self._documents = documents

    def apply(
        self,
        batch: KnowledgeAdoptionBatch,
        *,
        document_keys: tuple[str, ...] = (),
        write: bool = False,
    ) -> KnowledgeAdoptionReport:
        known = {item.document_key for item in batch.candidates}
        if set(document_keys) - known:
            raise ValueError("requested documents are not represented by qualified candidates")
        selected = set(document_keys) if document_keys else known
        by_document = defaultdict(list)
        for item in batch.candidates:
            if item.document_key in selected:
                by_document[item.document_key].append(item)
        pending: dict[str, EngineeringDocument] = {}
        results = []
        for key, candidates in sorted(by_document.items()):
            document = self._documents.load(DocumentKey(value=key))
            if document.key.value != key:
                raise ValueError(f"repository returned a different document: {key}")
            clauses = {clause.id.value: clause for clause in document.clauses}
            if len(clauses) != len(document.clauses):
                raise ValueError(f"duplicate clause ids in target document: {key}")
            for item in candidates:
                clause = clauses.get(item.clause_id)
                coordinate = f"{key}/{item.clause_id}"
                if clause is None:
                    raise ValueError(f"adoption target clause is missing: {coordinate}")
                if item.reference not in (clause.reference.clause, clause.reference.as_text()):
                    raise ValueError(f"adoption clause reference changed: {coordinate}")
                if (item.heading or "") != (clause.heading or ""):
                    raise ValueError(f"adoption clause heading changed: {coordinate}")
                if normalized_content_hash(clause.plain_text) != item.content_hash:
                    raise ValueError(f"adoption clause content changed: {coordinate}")
                if item.source_requirements:
                    ancestors = []
                    parent_id = clause.parent_id
                    visited = {clause.id.value}
                    while parent_id:
                        parent = clauses.get(parent_id.value)
                        if parent is None or parent.id.value in visited:
                            raise ValueError(f"adoption source ancestry changed: {coordinate}")
                        ancestors.append(parent)
                        visited.add(parent.id.value)
                        parent_id = parent.parent_id
                    current_source = project_source_structure(
                        clause,
                        document_key=key,
                        content_hash=item.content_hash,
                        ancestors=tuple(ancestors),
                    )
                    available = {fact.fingerprint for fact in current_source.facts}
                    if any(fact.fingerprint not in available for fact in item.source_requirements):
                        raise ValueError(
                            f"adoption taxonomy source/authority changed: {coordinate}"
                        )
                merged = merge_generated_enrichments(clause, item.patch, item.attributes)
                clauses[item.clause_id] = merged.clause
                results.append(
                    ClauseAdoptionResult(
                        document_key=key,
                        clause_id=item.clause_id,
                        changes=merged.changes,
                        not_evaluated=tuple(
                            path
                            for path in item.not_evaluated
                            if path not in {change.path for change in merged.changes}
                        ),
                    )
                )
            updated = document.model_copy(
                update={"clauses": tuple(clauses[item.id.value] for item in document.clauses)}
            )
            if updated != document:
                pending[key] = updated
        # All schema, coordinate and source checks above complete before writing.
        # Repository writes are atomic per document, not a multi-file transaction.
        if write:
            for document in pending.values():
                self._documents.save(document)
        counts = Counter(change.status for item in results for change in item.changes)
        counts["not_evaluated"] = sum(len(item.not_evaluated) for item in results)
        return KnowledgeAdoptionReport(
            source_id=batch.source_id,
            source_sha256=batch.source_sha256,
            write_requested=write,
            selected_clause_count=batch.selected_clause_count,
            unqualified_clause_count=batch.unqualified_clause_count,
            addressed_clause_count=len(results),
            changed_document_keys=tuple(pending),
            written_document_keys=tuple(pending) if write else (),
            status_counts=dict(sorted(counts.items())),
            clauses=tuple(results),
        )
