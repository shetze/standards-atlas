"""Materialize deterministic structural context for engineering documents."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.application.services.structural_profile_classifier import (
    StructuralProfileClassifier,
    StructuralProfileContext,
)
from standards_atlas.domain.model import (
    Clause,
    DocumentKey,
    EngineeringDocument,
    StructuralAncestor,
    StructuralContext,
    StructuralNodeKind,
    StructuralReferenceEdge,
    StructuralSiblingContext,
)


class StructuralTaxonomyResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    document: EngineeringDocument


class StructuralTaxonomyService:
    """Build a structure-only context graph without semantic interpretation."""

    def __init__(
        self,
        documents: EngineeringDocumentRepository,
        classifier: StructuralProfileClassifier | None = None,
    ) -> None:
        self._documents = documents
        self._classifier = classifier or StructuralProfileClassifier()

    def classify(self, document_key: str) -> StructuralTaxonomyResult:
        document = self._documents.load(DocumentKey(value=document_key))
        clauses = document.clauses
        by_id = {clause.id.value: clause for clause in clauses}
        children: dict[str | None, list[Clause]] = {}
        for clause in clauses:
            parent = clause.parent_id.value if clause.parent_id else None
            children.setdefault(parent, []).append(clause)

        updated: list[Clause] = []
        for clause in clauses:
            parent_key = clause.parent_id.value if clause.parent_id else None
            siblings = children.get(parent_key, [clause])
            index = next(i for i, item in enumerate(siblings) if item.id == clause.id)
            child_items = children.get(clause.id.value, [])
            node_kind = StructuralNodeKind.NODE if child_items else StructuralNodeKind.LEAF

            ancestors: list[StructuralAncestor] = []
            current = clause
            seen: set[str] = set()
            while current.parent_id is not None:
                parent_id = current.parent_id.value
                if parent_id in seen:
                    break
                seen.add(parent_id)
                parent = by_id.get(parent_id)
                if parent is None:
                    break
                ancestors.append(
                    StructuralAncestor(
                        clause_id=parent.id.value,
                        reference=parent.reference.clause,
                        heading=parent.title,
                    )
                )
                current = parent
            ancestors.reverse()

            reference_edges: list[StructuralReferenceEdge] = []
            for mention in clause.reference_mentions:
                if mention.targets:
                    for target in mention.targets:
                        reference_edges.append(
                            StructuralReferenceEdge(
                                source_clause_id=clause.id.value,
                                target_clause_id=target.clause_id,
                                target_reference=target.reference,
                                status=mention.status.value,
                                surface_text=mention.surface_text,
                            )
                        )
                else:
                    reference_edges.append(
                        StructuralReferenceEdge(
                            source_clause_id=clause.id.value,
                            target_reference=mention.reference,
                            status=mention.status.value,
                            surface_text=mention.surface_text,
                        )
                    )

            context_clause_ids = tuple(
                ancestor.clause_id
                for ancestor in ancestors
                if by_id[ancestor.clause_id].plain_text.strip()
            )
            structural_context = StructuralContext(
                node_kind=node_kind,
                ancestors=tuple(ancestors),
                sibling=StructuralSiblingContext(
                    index=index,
                    count=len(siblings),
                    is_first=index == 0,
                    is_last=index == len(siblings) - 1,
                    previous_clause_id=siblings[index - 1].id.value if index > 0 else None,
                    next_clause_id=(
                        siblings[index + 1].id.value if index + 1 < len(siblings) else None
                    ),
                ),
                child_clause_ids=tuple(item.id.value for item in child_items),
                contextual_content_clause_ids=context_clause_ids,
                references=tuple(reference_edges),
            )
            detected = self._classifier.classify(
                StructuralProfileContext(
                    reference=clause.reference.clause,
                    heading=clause.title or "",
                    text=clause.plain_text,
                )
            )
            existing = clause.structural_profile
            if existing is not None:
                detected = detected.model_copy(
                    update={
                        "canonical_section": detected.canonical_section
                        or existing.canonical_section,
                        "document_categories": existing.document_categories,
                        "domain_categories": existing.domain_categories,
                        "annex_status": detected.annex_status or existing.annex_status,
                        "semantic_sections": detected.semantic_sections
                        or existing.semantic_sections,
                    }
                )
            updated.append(
                clause.model_copy(
                    update={
                        "structural_profile": detected,
                        "structural_context": structural_context,
                    }
                )
            )
        result = document.model_copy(update={"clauses": tuple(updated)})
        self._documents.save(result)
        return StructuralTaxonomyResult(document=result)
