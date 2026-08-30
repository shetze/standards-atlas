"""Materialize CBox-oriented scope and reference routing enrichment."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from pydantic import BaseModel, ConfigDict

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    LlmResponseError,
    StructuredGenerationRequest,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseType,
    ContextRouting,
    DocumentKey,
    EngineeringDocument,
    GeneratedAttribute,
    GenerationMethod,
    ReferenceRole,
    ReferenceRouting,
    ReferenceTarget,
    ScopeDeclaration,
    ScopeReach,
)


@dataclass(frozen=True)
class ContextEnrichmentProgress:
    """Observable progress while contextual routing is enriched for one clause."""

    current: int
    total: int
    document_key: str
    clause_id: str
    clause_reference: str
    clause_title: str | None
    state: str
    elapsed_seconds: float | None = None


ContextEnrichmentProgressCallback = Callable[[ContextEnrichmentProgress], None]


class ContextEnrichmentResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    document: EngineeringDocument
    candidates: int
    clauses_enriched: int
    context_enrichment_failures: int = 0


class LlmContextRoutingEnricher:
    """Interpret only scope reach and reference routing for a clause.

    The output contract deliberately excludes semantic-classification targets such as
    statement function, knowledge kind, applicability function, and role semantics.
    """

    def __init__(
        self,
        gateway: LlmGateway,
        *,
        prompt: PromptDefinition,
        model: str | None = None,
    ) -> None:
        self._gateway = gateway
        self._prompt = prompt
        self._model = model

    @property
    def generator_id(self) -> str:
        return f"{self._prompt.task}/{self._prompt.version}"

    def enrich(self, *, clause: Clause, document: EngineeringDocument) -> ContextRouting:
        structural = clause.structural_context
        if structural is None:
            raise ValueError(
                f"Clause {clause.id.value} has no structural_context; run taxonomy first"
            )
        context_payload = {
            "document_key": document.key.value,
            "document_title": document.title,
            "reference": clause.reference.as_text(),
            "heading": clause.heading,
            "clause_type": clause.clause_type.value,
            "ancestors": [item.model_dump(mode="json") for item in structural.ancestors],
            "scope_mentions": [item.model_dump(mode="json") for item in structural.scope_mentions],
            "scope_edges": [item.model_dump(mode="json") for item in structural.scopes],
            "structural_references": [
                item.model_dump(mode="json") for item in structural.references
            ],
            "reference_mentions": [
                item.model_dump(mode="json") for item in clause.reference_mentions
            ],
        }
        values = {
            "content": clause.plain_text,
            "context_json": json.dumps(context_payload, ensure_ascii=False, sort_keys=True),
            **context_payload,
        }
        try:
            user_prompt = self._prompt.user_template.format(**values)
        except KeyError as exc:
            raise ValueError(
                f"context enrichment prompt references unavailable field: {exc.args[0]}"
            ) from exc

        request = StructuredGenerationRequest(
            task=self._prompt.task,
            system_prompt=self._prompt.system_prompt,
            user_prompt=user_prompt,
            output_schema=self._prompt.output_schema,
            prompt_version=self._prompt.version,
            model=self._model,
            temperature=0.0,
            seed=0,
            max_tokens=1024,
            reasoning_enabled=False,
        )
        try:
            result = self._gateway.generate_structured(request)
        except LlmResponseError as error:
            if error.finish_reason != "length":
                raise
            result = self._gateway.generate_structured(
                replace(
                    request,
                    system_prompt=(
                        request.system_prompt
                        + " The previous response was truncated. Return only the compact JSON "
                        "object required by the schema, with no explanations or extra fields."
                    ),
                    max_tokens=2048,
                )
            )
        return _context_routing_from_payload(clause.id.value, result.value)


def _context_routing_from_payload(
    source_clause_id: str,
    payload: Mapping[str, object],
) -> ContextRouting:
    try:
        return _validated_context_routing_from_payload(source_clause_id, payload)
    except (TypeError, ValueError) as exc:
        raise LlmResponseError("context enrichment response violates routing invariants") from exc


def _validated_context_routing_from_payload(
    source_clause_id: str,
    payload: Mapping[str, object],
) -> ContextRouting:
    scopes = []
    for item in payload.get("scope_declarations", ()):
        if not isinstance(item, Mapping):
            raise LlmResponseError("scope declaration must be an object")
        reaches = tuple(ScopeReach.model_validate(value) for value in item.get("reaches", ()))
        scopes.append(
            ScopeDeclaration(
                source_clause_id=source_clause_id,
                reaches=reaches,
                conditions=tuple(str(value) for value in item.get("conditions", ())),
                exclusions=tuple(str(value) for value in item.get("exclusions", ())),
                qualifications=tuple(str(value) for value in item.get("qualifications", ())),
                evidence=tuple(str(value) for value in item.get("evidence", ())),
            )
        )

    references = []
    for item in payload.get("reference_routings", ()):
        if not isinstance(item, Mapping):
            raise LlmResponseError("reference routing must be an object")
        references.append(
            ReferenceRouting(
                source_clause_id=source_clause_id,
                target=ReferenceTarget.model_validate(item.get("target")),
                role=ReferenceRole(str(item.get("role"))),
                evidence=tuple(str(value) for value in item.get("evidence", ())),
            )
        )
    return ContextRouting(scopes=tuple(scopes), references=tuple(references))


def _is_context_candidate(clause: Clause) -> bool:
    """Return whether a clause contains evidence worth contextual interpretation."""

    structural = clause.structural_context
    if structural is None:
        return False
    return bool(
        clause.clause_type == ClauseType.SCOPE
        or clause.reference_mentions
        or structural.scope_mentions
        or structural.scopes
        or structural.references
    )


class ContextEnrichmentService:
    """Persist focused CBox enrichment without pre-classifying clause semantics."""

    def __init__(
        self,
        *,
        documents: EngineeringDocumentRepository,
        enricher: LlmContextRoutingEnricher,
        progress: ContextEnrichmentProgressCallback | None = None,
    ) -> None:
        self._documents = documents
        self._enricher = enricher
        self._progress = progress

    def enrich(self, document_key: str) -> ContextEnrichmentResult:
        document = self._documents.load(DocumentKey(value=document_key))
        for clause in document.clauses:
            if clause.structural_context is None:
                raise ValueError(
                    f"Clause {clause.id.value} has no structural_context; run taxonomy first"
                )

        candidates = tuple(clause for clause in document.clauses if _is_context_candidate(clause))
        candidate_ids = {clause.id.value for clause in candidates}
        updated = []
        enriched_count = 0
        failures = 0
        current = 0
        total = len(candidates)

        for clause in document.clauses:
            if clause.id.value not in candidate_ids:
                updated.append(clause)
                continue
            current += 1
            if self._progress is not None:
                self._progress(
                    ContextEnrichmentProgress(
                        current=current,
                        total=total,
                        document_key=document.key.value,
                        clause_id=clause.id.value,
                        clause_reference=clause.reference.clause,
                        clause_title=clause.heading,
                        state="started",
                    )
                )
            started = time.monotonic()
            try:
                routing = self._enricher.enrich(clause=clause, document=document)
            except LlmResponseError:
                failures += 1
                updated.append(clause)
                state = "partial"
            else:
                enriched_clause = clause.with_context_routing(routing).mark_generated(
                    GeneratedAttribute(
                        path="enrichments.context_routing",
                        generator=self._enricher.generator_id,
                        method=GenerationMethod.LLM,
                        evidence=_source_evidence(clause),
                    )
                )
                updated.append(enriched_clause)
                enriched_count += 1
                state = "ok"

            if self._progress is not None:
                self._progress(
                    ContextEnrichmentProgress(
                        current=current,
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
        return ContextEnrichmentResult(
            document=result,
            candidates=total,
            clauses_enriched=enriched_count,
            context_enrichment_failures=failures,
        )


def _source_evidence(clause: Clause) -> tuple[str, ...]:
    structural = clause.structural_context
    scope_evidence = (
        tuple(item.surface_text for item in structural.scope_mentions) if structural else ()
    )
    reference_evidence = tuple(item.surface_text for item in clause.reference_mentions)
    return tuple(dict.fromkeys((*scope_evidence, *reference_evidence)))
