"""Apply a qualified ontology classifier to persisted engineering documents."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from standards_atlas.application.ontology import (
    OntologyContext,
    OntologyEngine,
    OntologyProfile,
    RoleSemanticsClassifier,
)
from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.application.ports.llm_gateway import LlmResponseError
from standards_atlas.domain.model import (
    ApplicabilityFunction,
    DocumentKey,
    EngineeringDocument,
    KnowledgeKind,
    ProcessFunction,
    StatementFunction,
)


@dataclass(frozen=True)
class OntologyClassificationProgress:
    """Observable progress for one clause in document ontology classification."""

    current: int
    total: int
    document_key: str
    clause_id: str
    clause_reference: str
    clause_title: str | None
    state: str
    elapsed_seconds: float | None = None


OntologyProgressCallback = Callable[[OntologyClassificationProgress], None]


class OntologyClassificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    document: EngineeringDocument
    clauses_classified: int
    role_semantics_failures: int = 0
    ontology_classification_failures: int = 0


class OntologyClassificationService:
    """Materialize semantic ontology dimensions after structural taxonomy."""

    def __init__(
        self,
        *,
        documents: EngineeringDocumentRepository,
        engine: OntologyEngine,
        profile: OntologyProfile,
        classifier_id: str = "qualified-llm",
        role_semantics: RoleSemanticsClassifier | None = None,
        progress: OntologyProgressCallback | None = None,
    ) -> None:
        self._documents = documents
        self._engine = engine
        self._profile = profile
        self._classifier_id = classifier_id
        self._role_semantics = role_semantics
        self._progress = progress

    def classify(self, document_key: str) -> OntologyClassificationResult:
        document = self._documents.load(DocumentKey(value=document_key))
        clauses_by_id = {item.id.value: item for item in document.clauses}
        updated = []
        classified = 0
        role_semantics_failures = 0
        ontology_classification_failures = 0
        total = len(document.clauses)
        for index, clause in enumerate(document.clauses, start=1):
            if clause.structural_context is None:
                raise ValueError(
                    f"Clause {clause.id.value} has no structural_context; run taxonomy first"
                )
            contextual_content = [
                clauses_by_id[item].plain_text
                for item in clause.structural_context.contextual_content_clause_ids
                if item in clauses_by_id and clauses_by_id[item].plain_text.strip()
            ]
            if self._progress is not None:
                self._progress(
                    OntologyClassificationProgress(
                        current=index,
                        total=total,
                        document_key=document.key.value,
                        clause_id=clause.id.value,
                        clause_reference=clause.reference.clause,
                        clause_title=clause.title,
                        state="started",
                    )
                )
            started = time.monotonic()
            context = OntologyContext(
                content=clause.plain_text,
                structural_context=clause.structural_context.model_dump(mode="json"),
                metadata={
                    "document_key": document.key.value,
                    "document_title": document.title,
                    "clause_id": clause.id.value,
                    "reference": clause.reference.clause,
                    "title": clause.title,
                    "structural_profile": (
                        clause.structural_profile.model_dump(mode="json")
                        if clause.structural_profile is not None
                        else None
                    ),
                    "contextual_content": contextual_content,
                    "reference_mentions": [
                        item.model_dump(mode="json") for item in clause.reference_mentions
                    ],
                },
            )
            ontology_failed = False
            try:
                results = self._engine.classify(
                    profile=self._profile,
                    classifier_id=self._classifier_id,
                    context=context,
                )
            except LlmResponseError:
                ontology_classification_failures += 1
                ontology_failed = True
                results = ()
            values = {item.dimension: item.values for item in results}
            current = clause.semantic_classification
            role_result = None
            role_failed = False
            if self._role_semantics is not None:
                try:
                    role_result = self._role_semantics.classify(context)
                except LlmResponseError:
                    role_failed = True
                    # Role semantics is one semantic dimension. A malformed response after the
                    # classifier's bounded retry must not discard successful classifications
                    # from the remaining dimensions or abort the complete document workflow.
                    role_semantics_failures += 1
            semantic = current
            if not ontology_failed:
                semantic = current.model_copy(
                    update={
                        "statement_functions": tuple(
                            StatementFunction(item)
                            for item in values.get("statement_functions", ())
                        ),
                        "knowledge_kinds": tuple(
                            KnowledgeKind(item) for item in values.get("knowledge_kinds", ())
                        ),
                        "process_functions": tuple(
                            ProcessFunction(item) for item in values.get("process_functions", ())
                        ),
                        "applicability_functions": tuple(
                            ApplicabilityFunction(item)
                            for item in values.get("applicability_functions", ())
                        ),
                    }
                )
            if role_result is not None:
                semantic = semantic.model_copy(
                    update={
                        "role_semantics_present": role_result.present,
                        "role_relations": role_result.relations,
                        "role_relation_types": tuple(
                            dict.fromkeys(
                                item.relation
                                for item in role_result.relations
                                if item.relation is not None
                            )
                        ),
                    }
                )
            updated.append(clause.model_copy(update={"semantic_classification": semantic}))
            if not ontology_failed:
                classified += 1
            if self._progress is not None:
                state = "partial" if ontology_failed or role_failed else "ok"
                self._progress(
                    OntologyClassificationProgress(
                        current=index,
                        total=total,
                        document_key=document.key.value,
                        clause_id=clause.id.value,
                        clause_reference=clause.reference.clause,
                        clause_title=clause.title,
                        state=state,
                        elapsed_seconds=time.monotonic() - started,
                    )
                )
        result = document.model_copy(update={"clauses": tuple(updated)})
        self._documents.save(result)
        return OntologyClassificationResult(
            document=result,
            clauses_classified=classified,
            role_semantics_failures=role_semantics_failures,
            ontology_classification_failures=ontology_classification_failures,
        )
