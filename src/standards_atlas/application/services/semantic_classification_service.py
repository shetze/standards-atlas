"""Apply qualified semantic classification to persisted engineering documents."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from standards_atlas.application.ontology import RoleSemanticsClassifier
from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.application.ports.llm_gateway import LlmResponseError
from standards_atlas.application.semantic_classification import (
    SemanticClassificationContext,
    SemanticClassificationEngine,
    SemanticProfile,
)
from standards_atlas.domain.model import (
    ApplicabilityFunction,
    DocumentKey,
    EngineeringDocument,
    GeneratedAttribute,
    GenerationMethod,
    KnowledgeKind,
    ProcessFunction,
    SemanticClassification,
    StatementFunction,
)


@dataclass(frozen=True)
class SemanticClassificationProgress:
    """Observable progress for one clause in document semantic classification."""

    current: int
    total: int
    document_key: str
    clause_id: str
    clause_reference: str
    clause_title: str | None
    state: str
    elapsed_seconds: float | None = None


SemanticClassificationProgressCallback = Callable[[SemanticClassificationProgress], None]


def _unique(values: Iterable[object]) -> tuple[object, ...]:
    """Return values once while preserving their semantic input order."""

    return tuple(dict.fromkeys(values))


def _unique_role_relations(values: Iterable[object]) -> tuple[object, ...]:
    """Deduplicate role relations by the same semantic key enforced by the domain model."""

    unique: list[object] = []
    seen: set[tuple[object, object, object]] = set()
    for item in values:
        if isinstance(item, Mapping):
            key = (item.get("actor"), item.get("relation_class"), item.get("target"))
        else:
            key = (item.actor, item.relation_class, item.target)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


def _canonicalize_semantic_payload(payload: dict[str, object]) -> dict[str, object]:
    """Canonicalize set-like semantic dimensions before strict model validation."""

    result = dict(payload)
    for field in (
        "statement_functions",
        "knowledge_kinds",
        "process_functions",
        "applicability_functions",
        "role_relation_types",
    ):
        result[field] = _unique(result.get(field, ()))
    result["role_relations"] = _unique_role_relations(result.get("role_relations", ()))
    return result


def _validated_semantic_merge(
    current: SemanticClassification,
    update: dict[str, object],
) -> SemanticClassification:
    """Apply one semantic-dimension update atomically and revalidate all invariants."""

    payload = current.model_dump(mode="python")
    payload.update(update)
    return SemanticClassification.model_validate(_canonicalize_semantic_payload(payload))


class SemanticClassificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    document: EngineeringDocument
    clauses_classified: int
    role_semantics_failures: int = 0
    semantic_classification_failures: int = 0


class SemanticClassificationService:
    """Materialize semantic profile dimensions after structural taxonomy."""

    def __init__(
        self,
        *,
        documents: EngineeringDocumentRepository,
        engine: SemanticClassificationEngine,
        profile: SemanticProfile,
        classifier_id: str = "qualified-llm",
        role_semantics: RoleSemanticsClassifier | None = None,
        progress: SemanticClassificationProgressCallback | None = None,
    ) -> None:
        self._documents = documents
        self._engine = engine
        self._profile = profile
        self._classifier_id = classifier_id
        self._role_semantics = role_semantics
        self._progress = progress

    def classify(self, document_key: str) -> SemanticClassificationResult:
        document = self._documents.load(DocumentKey(value=document_key))
        clauses_by_id = {item.id.value: item for item in document.clauses}
        updated = []
        classified = 0
        role_semantics_failures = 0
        semantic_classification_failures = 0
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
                    SemanticClassificationProgress(
                        current=index,
                        total=total,
                        document_key=document.key.value,
                        clause_id=clause.id.value,
                        clause_reference=clause.reference.clause,
                        clause_title=clause.heading,
                        state="started",
                    )
                )
            started = time.monotonic()
            context = SemanticClassificationContext(
                content=clause.plain_text,
                structural_context=clause.structural_context.model_dump(mode="json"),
                metadata={
                    "document_key": document.key.value,
                    "document_title": document.title,
                    "clause_id": clause.id.value,
                    "reference": clause.reference.clause,
                    "title": clause.heading,
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
                semantic_classification_failures += 1
                ontology_failed = True
                results = ()
            values = {item.dimension: item.values for item in results}
            presence = {
                item.dimension: item.presence for item in results if item.presence is not None
            }
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
                applicability_functions = tuple(
                    ApplicabilityFunction(item)
                    for item in values.get("applicability_functions", ())
                )
                semantic = _validated_semantic_merge(
                    current,
                    {
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
                        # Applicability is one coupled semantic dimension. Presence and subtype
                        # must be replaced atomically so a stale presence bit cannot survive a
                        # successful subtype classification (or vice versa).
                        "applicability_present": presence.get(
                            "applicability_functions", bool(applicability_functions)
                        ),
                        "applicability_functions": applicability_functions,
                    },
                )
            if role_result is not None:
                role_relations = role_result.relations if role_result.present else ()
                role_relation_types = tuple(
                    dict.fromkeys(
                        item.relation for item in role_relations if item.relation is not None
                    )
                )
                semantic = _validated_semantic_merge(
                    semantic,
                    {
                        # Role presence, relation types, and resolved relations are another
                        # coupled dimension and therefore move together.
                        "role_semantics_present": role_result.present,
                        "role_relations": role_relations,
                        "role_relation_types": role_relation_types,
                    },
                )
            # Revalidate the complete classification before it crosses the persistence
            # boundary. This catches any future coupled-dimension merge bug at its source.
            semantic = _validated_semantic_merge(semantic, {})
            enriched_clause = clause.with_semantic_classification(semantic)
            generated: list[GeneratedAttribute] = []
            if not ontology_failed:
                generated.extend(
                    GeneratedAttribute(
                        path=f"enrichments.semantic.{dimension}",
                        generator=self._classifier_id,
                        method=GenerationMethod.LLM,
                    )
                    for dimension in (
                        "statement_functions",
                        "knowledge_kinds",
                        "process_functions",
                        "applicability_present",
                        "applicability_functions",
                    )
                )
            if role_result is not None:
                generated.extend(
                    GeneratedAttribute(
                        path=f"enrichments.semantic.{dimension}",
                        generator=self._classifier_id,
                        method=GenerationMethod.LLM,
                    )
                    for dimension in (
                        "role_semantics_present",
                        "role_relation_types",
                        "role_relations",
                    )
                )
            if generated:
                enriched_clause = enriched_clause.mark_generated(*generated)
            updated.append(enriched_clause)
            if not ontology_failed:
                classified += 1
            if self._progress is not None:
                state = "partial" if ontology_failed or role_failed else "ok"
                self._progress(
                    SemanticClassificationProgress(
                        current=index,
                        total=total,
                        document_key=document.key.value,
                        clause_id=clause.id.value,
                        clause_reference=clause.reference.clause,
                        clause_title=clause.heading,
                        state=state,
                        elapsed_seconds=time.monotonic() - started,
                    )
                )
        result = document.model_copy(update={"clauses": tuple(updated)})
        self._documents.save(result)
        return SemanticClassificationResult(
            document=result,
            clauses_classified=classified,
            role_semantics_failures=role_semantics_failures,
            semantic_classification_failures=semantic_classification_failures,
        )
