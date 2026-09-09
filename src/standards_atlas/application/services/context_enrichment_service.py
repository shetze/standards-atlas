"""Materialize deterministic subject context plus scope/reference routing."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from pydantic import BaseModel, ConfigDict

from standards_atlas.application.context import (
    ClauseSubjectIdentification,
    DeterministicSubjectIdentifier,
    SubjectCandidateVocabularyBuilder,
    normalize_context_routing_targets,
)
from standards_atlas.application.context.canonical_cbox import context_fingerprint
from standards_atlas.application.context.information_routing import (
    INFORMATION_ROUTING_POLICY,
    InformationRoutingPolicy,
)
from standards_atlas.application.context.scope_targets import ScopeTargetResolver
from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    LlmResponseError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from standards_atlas.application.references.extractor import (
    REFERENCE_EXTRACTOR_VERSION,
    extract_reference_mentions,
    refresh_document_references,
    resolve_reference_mentions,
)
from standards_atlas.application.references.resolution import DocumentReferenceIndex
from standards_atlas.domain.model import (
    Clause,
    ClauseSubjectContext,
    ClauseType,
    ContextRouting,
    DocumentKey,
    EngineeringDocument,
    GeneratedAttribute,
    GenerationMethod,
    PrimarySubjectContext,
    ReferenceRole,
    ReferenceRouting,
    ReferenceTarget,
    ScopeDeclaration,
    ScopeReach,
    SubjectContextEvidence,
)
from standards_atlas.domain.model.enrichment_patch import (
    ClauseEnrichmentPatch,
    merge_generated_enrichments,
)
from standards_atlas.domain.model.knowledge_state import DecisionSupport


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
    detail: str | None = None


ContextEnrichmentProgressCallback = Callable[[ContextEnrichmentProgress], None]


class ContextEnrichmentResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    document: EngineeringDocument
    candidates: int
    clauses_enriched: int
    subject_clauses: int = 0
    subjects_identified: int = 0
    subjects_ambiguous: int = 0
    context_enrichment_failures: int = 0
    routing_reused: int = 0
    routing_outcomes: tuple[dict[str, object], ...] = ()
    routing_failures: tuple[dict[str, object], ...] = ()
    unresolved_scope_targets: tuple[dict[str, object], ...] = ()
    unresolved_reference_targets: tuple[dict[str, object], ...] = ()
    routing_corrections: tuple[dict[str, object], ...] = ()


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
        max_tokens: int = 1024,
        retry_max_tokens: int = 2048,
        scope_documents: tuple[EngineeringDocument, ...] = (),
    ) -> None:
        self._gateway = gateway
        self._prompt = prompt
        self._model = model
        self._max_tokens = max_tokens
        self._retry_max_tokens = retry_max_tokens
        self._scope_documents = scope_documents
        self.semantic_diagnostics: tuple[dict, ...] = ()

    @property
    def generator_id(self) -> str:
        model = self._model or "default-model"
        return f"{self._prompt.task}/{self._prompt.version}@{model}"

    def _request(
        self,
        *,
        clause: Clause,
        document: EngineeringDocument,
    ) -> StructuredGenerationRequest:
        structural = clause.structural_context
        if structural is None:
            raise ValueError(
                f"Clause {clause.id.value} has no structural_context; run taxonomy first"
            )
        # Rebuild the bounded citation context from source text: older baseline
        # mentions may predate annex/list/range support or contain stale targets.
        mentions = resolve_reference_mentions(
            extract_reference_mentions(clause.plain_text),
            clause.id.value,
            DocumentReferenceIndex(document),
        )
        context_payload = {
            "source_clause_id": clause.id.value,
            "document_key": document.key.value,
            "document_title": document.title,
            "reference": clause.reference.as_text(),
            "heading": clause.heading,
            "clause_type": clause.clause_type.value,
            "ancestors": [item.model_dump(mode="json") for item in structural.ancestors],
            "scope_mentions": [item.model_dump(mode="json") for item in structural.scope_mentions],
            "scope_edges": [item.model_dump(mode="json") for item in structural.scopes],
            "structural_references": [
                {
                    "surface_text": mention.surface_text,
                    "status": mention.status.value,
                    "targets": [target.model_dump(mode="json") for target in mention.targets],
                }
                for mention in mentions
            ],
            "reference_mentions": [item.model_dump(mode="json") for item in mentions],
            "subject_context": clause.subject_context.model_dump(mode="json"),
        }
        metadata = {
            "reference_extraction": REFERENCE_EXTRACTOR_VERSION,
            "routing_semantics": INFORMATION_ROUTING_POLICY,
        }
        if self._prompt.version == "context-routing-v3":
            resolver = ScopeTargetResolver(document, self._scope_documents)
            context_payload["scope_target_documents"] = resolver.catalog()
            metadata["scope_target_catalog_sha256"] = resolver.fingerprint()
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

        return StructuredGenerationRequest(
            task=self._prompt.task,
            system_prompt=self._prompt.system_prompt,
            user_prompt=user_prompt,
            output_schema=self._prompt.output_schema,
            prompt_version=self._prompt.version,
            model=self._model,
            temperature=0.0,
            seed=0,
            max_tokens=self._max_tokens,
            reasoning_enabled=False,
            metadata=metadata,
        )

    def input_fingerprint(self, *, clause: Clause, document: EngineeringDocument) -> str:
        request = self._request(clause=clause, document=document)
        return context_fingerprint(
            {
                "contract": "context-routing-input-v1",
                "reference_resolution": "document-coordinates-v4",
                "generator": self.generator_id,
                "system": request.system_prompt,
                "prompt": request.user_prompt,
                "schema": dict(request.output_schema),
                "model": request.model,
                "max_tokens": request.max_tokens,
                "retry_max_tokens": self._retry_max_tokens,
                **dict(request.metadata),
            }
        )

    def enrich(self, *, clause: Clause, document: EngineeringDocument) -> ContextRouting:
        self.semantic_diagnostics = ()
        request = self._request(clause=clause, document=document)
        try:
            result = self._generate_with_truncation_retry(request)
            routing = self._routing(clause, document, result.value)
        except LlmResponseError as first_error:
            retry_hint = (
                "Scope reaches have only reference and include_descendants. Preserve the complete "
                "target citation, including an explicit Parts label for part lists. Never emit "
                "kind, part, document_key or clause_id in reaches. Do not erase targets or "
                "return empty arrays just to suppress the validation error. "
                if self._prompt.version == "context-routing-v3"
                else "For document scope do not set part/clause/reference; for part scope set "
                "only part; for subtree/clause scope provide an exact target reference. "
            )
            rejected = first_error.raw_content
            retry_request = replace(
                request,
                user_prompt=(
                    request.user_prompt
                    + "\n\nRejected output (diagnostic data, not source evidence):\n"
                    + json.dumps(
                        {"response": rejected, "validation_error": str(first_error)},
                        ensure_ascii=False,
                    )
                ),
                system_prompt=(
                    request.system_prompt
                    + " The previous structured response was unusable. Re-evaluate the clause "
                    "and return only JSON that satisfies every routing invariant. "
                    + retry_hint
                    + "Do not add explanations. Validation failure: "
                    + str(first_error)
                ),
                max_tokens=self._retry_max_tokens,
                metadata={**request.metadata, "corrective_retry": "routing-invariants-v1"},
            )
            try:
                result = self._generate_with_truncation_retry(retry_request)
                routing = self._routing(clause, document, result.value)
            except LlmResponseError as retry_error:
                raise LlmResponseError(
                    "context enrichment response remains invalid after corrective retry: "
                    f"{retry_error}",
                    raw_content=retry_error.raw_content,
                    raw_response={
                        "first_error": str(first_error),
                        "first_response": first_error.raw_content,
                        "retry_error": str(retry_error),
                        "retry_response": retry_error.raw_content,
                    },
                    finish_reason=retry_error.finish_reason,
                ) from retry_error
        return normalize_context_routing_targets(routing, document)

    def _routing(
        self, clause: Clause, document: EngineeringDocument, payload: Mapping[str, object]
    ) -> ContextRouting:
        resolver = (
            ScopeTargetResolver(document, self._scope_documents)
            if self._prompt.version == "context-routing-v3"
            else None
        )
        diagnostics: list[dict] = []
        routing = _context_routing_from_payload(
            clause.id.value,
            payload,
            scope_resolver=resolver,
            information_policy=InformationRoutingPolicy(document, self._scope_documents),
            diagnostics=diagnostics,
        )
        self.semantic_diagnostics = tuple(diagnostics)
        return routing

    def _generate_with_truncation_retry(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        try:
            return self._gateway.generate_structured(request)
        except LlmResponseError as error:
            if error.finish_reason != "length":
                raise
            return self._gateway.generate_structured(
                replace(
                    request,
                    system_prompt=(
                        request.system_prompt
                        + " The previous response was truncated. Return only the compact JSON "
                        "object required by the schema, with no explanations or extra fields."
                    ),
                    max_tokens=self._retry_max_tokens,
                    metadata={**request.metadata, "corrective_retry": "truncation-v1"},
                )
            )


def _context_routing_from_payload(
    source_clause_id: str,
    payload: Mapping[str, object],
    *,
    scope_resolver: ScopeTargetResolver | None = None,
    information_policy: InformationRoutingPolicy | None = None,
    diagnostics: list[dict] | None = None,
) -> ContextRouting:
    try:
        return _validated_context_routing_from_payload(
            source_clause_id,
            payload,
            scope_resolver=scope_resolver,
            information_policy=information_policy,
            diagnostics=diagnostics,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LlmResponseError(
            f"context enrichment response violates routing invariants: {exc}",
            raw_content=json.dumps(dict(payload), ensure_ascii=False),
        ) from exc


def _validated_context_routing_from_payload(
    source_clause_id: str,
    payload: Mapping[str, object],
    *,
    scope_resolver: ScopeTargetResolver | None = None,
    information_policy: InformationRoutingPolicy | None = None,
    diagnostics: list[dict] | None = None,
) -> ContextRouting:
    scopes = []
    for item in payload.get("scope_declarations", ()):
        if not isinstance(item, Mapping):
            raise LlmResponseError("scope declaration must be an object")
        if scope_resolver is None:
            reaches = tuple(ScopeReach.model_validate(value) for value in item.get("reaches", ()))
        else:
            # Interpret the evidence before attempting to address alleged scopes.
            # Informational citations to uncatalogued documents are valid references,
            # not grounds for failing scope-address construction.
            reaches = tuple(_scope_transport_reach(value) for value in item.get("reaches", ()))
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
    routing = ContextRouting(scopes=tuple(scopes), references=tuple(references))
    if information_policy is None and scope_resolver is not None:
        information_policy = InformationRoutingPolicy(
            scope_resolver.document, scope_resolver.documents.values()
        )
    if information_policy is not None:
        semantic_diagnostics: list[dict] = []
        routing = information_policy.normalize(routing, diagnostics=semantic_diagnostics)
        if diagnostics is not None:
            diagnostics.extend(semantic_diagnostics)
        if any(item["status"] == "requires_review" for item in semantic_diagnostics):
            raise ValueError(
                "scope evidence establishes an informational reference, but the source or "
                "modifiers also contain unverified/governing material. Quote the direct "
                "governing statement for each scope; do not attach unrelated paragraphs "
                "to a reading list. Keep informational citations in reference_routings."
            )
    if scope_resolver is not None:
        routing = routing.model_copy(
            update={
                "scopes": tuple(
                    scope.model_copy(
                        update={
                            "reaches": tuple(
                                target
                                for reach in scope.reaches
                                for target in scope_resolver.resolve(
                                    reach.reference or "",
                                    include_descendants=reach.kind.value == "subtree",
                                    source_clause_id=source_clause_id,
                                    evidence=scope.evidence,
                                )
                            )
                        }
                    )
                    for scope in routing.scopes
                )
            }
        )
    return routing


def _scope_transport_reach(value: Mapping[str, object]) -> ScopeReach:
    if not isinstance(value, Mapping):
        raise TypeError("scope reach must be an object")
    if not isinstance(value.get("reference"), str) or not value["reference"].strip():
        raise ValueError("scope target reference must be a non-empty string")
    if not isinstance(value.get("include_descendants"), bool):
        raise ValueError("scope include_descendants must be a boolean")
    return ScopeReach(
        kind="subtree" if value["include_descendants"] else "clause",
        reference=value["reference"],
    )


def _is_context_candidate(clause: Clause) -> bool:
    """Return whether a clause contains evidence worth contextual interpretation."""

    structural = clause.structural_context
    if structural is None:
        return False
    return bool(
        clause.clause_type == ClauseType.SCOPE
        or clause.reference_mentions
        or extract_reference_mentions(clause.plain_text)
        or clause.context_routing.references
        or clause.context_routing.scopes
        or structural.scope_mentions
        or structural.scopes
        or structural.references
    )


class ContextEnrichmentService:
    """Persist deterministic subject context plus focused LLM routing enrichment."""

    def __init__(
        self,
        *,
        documents: EngineeringDocumentRepository,
        enricher: LlmContextRoutingEnricher,
        progress: ContextEnrichmentProgressCallback | None = None,
        fresh: bool = False,
        retry_clause_ids: tuple[str, ...] = (),
    ) -> None:
        self._documents = documents
        self._enricher = enricher
        self._progress = progress
        self._fresh = fresh
        self._retry_clause_ids = frozenset(retry_clause_ids)

    def enrich(self, document_key: str) -> ContextEnrichmentResult:
        original_document = self._documents.load(DocumentKey(value=document_key))
        document = refresh_document_references(original_document)
        for clause in document.clauses:
            if clause.structural_context is None:
                raise ValueError(
                    f"Clause {clause.id.value} has no structural_context; run taxonomy first"
                )

        documents = self._documents.list()
        information_policy = InformationRoutingPolicy(document, documents)
        routing_corrections: list[dict] = []
        vocabulary = SubjectCandidateVocabularyBuilder().build(documents)
        subject_report = DeterministicSubjectIdentifier().identify((document,), vocabulary)
        subjects_by_clause = {item.clause_id: item for item in subject_report.results}

        candidates = tuple(clause for clause in document.clauses if _is_context_candidate(clause))
        candidate_ids = {clause.id.value for clause in candidates}
        updated = []
        enriched_ids: set[str] = set()
        failures = 0
        routing_failures: list[dict[str, object]] = []
        routing_outcomes: list[dict[str, object]] = []
        reused = 0
        current = 0
        total = len(candidates)

        for clause in document.clauses:
            subject_result = subjects_by_clause[clause.id.value]
            subject_context = _subject_context(subject_result)
            contextual_clause = merge_generated_enrichments(
                clause,
                ClauseEnrichmentPatch(subject_context=subject_context),
                (
                    GeneratedAttribute(
                        path="enrichments.subject_context",
                        generator="subject-identification/1.0",
                        method=GenerationMethod.DETERMINISTIC,
                        evidence=(
                            (subject_result.primary_subject.evidence.source_text,)
                            if subject_result.primary_subject is not None
                            else subject_result.ambiguous_candidates
                        ),
                    ),
                ),
            ).clause
            if subject_result.primary_subject is not None or subject_result.ambiguous_candidates:
                enriched_ids.add(clause.id.value)

            outcome = {
                "clause_id": clause.id.value,
                "reference": clause.reference.as_text(),
                "status": "not_candidate",
            }
            routing_outcomes.append(outcome)
            if clause.id.value not in candidate_ids:
                updated.append(contextual_clause)
                continue
            current += 1
            path = "enrichments.context_routing"
            fingerprint_fn = getattr(self._enricher, "input_fingerprint", None)
            fingerprint = (
                fingerprint_fn(clause=contextual_clause, document=document)
                if callable(fingerprint_fn)
                else None
            )
            previous = next(
                (item for item in clause.provenance.generated_attributes if item.path == path), None
            )
            reusable = (
                not self._fresh
                and clause.id.value not in self._retry_clause_ids
                and fingerprint is not None
                and previous is not None
                and previous.availability == "known"
                and previous.decision is not None
                and previous.decision.rule == "context-routing-input-v1"
                and previous.decision.source_sha256 == fingerprint
            )
            outcome["input_fingerprint"] = fingerprint
            if clause.provenance.protection(path) or reusable:
                outcome["status"] = "protected" if clause.provenance.protection(path) else "reused"
                if reusable and previous is not None and not clause.provenance.protection(path):
                    # Reuse the provider result, not a stale/unverified target ID.
                    # Deterministic routing repairs need no new model call and
                    # retain the original evidence, role and generation provenance.
                    contextual_clause = merge_generated_enrichments(
                        contextual_clause,
                        ClauseEnrichmentPatch(
                            context_routing=normalize_context_routing_targets(
                                information_policy.normalize(
                                    contextual_clause.context_routing,
                                    diagnostics=routing_corrections,
                                ),
                                document,
                            )
                        ),
                        (previous,),
                    ).clause
                updated.append(contextual_clause)
                reused += 1
                if self._progress is not None:
                    self._progress(
                        ContextEnrichmentProgress(
                            current=current,
                            total=total,
                            document_key=document.key.value,
                            clause_id=clause.id.value,
                            clause_reference=clause.reference.clause,
                            clause_title=clause.heading,
                            state="reused",
                            elapsed_seconds=0.0,
                        )
                    )
                continue
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
            failure_detail = None
            try:
                generated_routing = self._enricher.enrich(
                    clause=contextual_clause, document=document
                )
                routing_corrections.extend(getattr(self._enricher, "semantic_diagnostics", ()))
                routing = normalize_context_routing_targets(
                    information_policy.normalize(
                        generated_routing, diagnostics=routing_corrections
                    ),
                    document,
                )
            except LlmResponseError as error:
                failures += 1
                outcome.update(
                    status="failed",
                    error=str(error),
                    retained_previous_value=bool(
                        previous is not None
                        or clause.context_routing.scopes
                        or clause.context_routing.references
                    ),
                    retained_input_fingerprint=(
                        previous.decision.source_sha256
                        if previous is not None and previous.decision is not None
                        else None
                    ),
                )
                updated.append(contextual_clause)
                state = "partial"
                failure_detail = str(error)
                routing_failures.append(
                    {
                        "clause_id": clause.id.value,
                        "reference": clause.reference.as_text(),
                        "generator": self._enricher.generator_id,
                        "input_fingerprint": fingerprint,
                        "error": str(error),
                        "rejected_content": error.raw_content,
                        "attempts": error.raw_response,
                    }
                )
            else:
                enriched_clause = merge_generated_enrichments(
                    contextual_clause,
                    ClauseEnrichmentPatch(context_routing=routing),
                    (
                        GeneratedAttribute(
                            path="enrichments.context_routing",
                            generator=self._enricher.generator_id,
                            method=GenerationMethod.LLM,
                            evidence=_source_evidence(clause),
                            decision=(
                                DecisionSupport(
                                    rule="context-routing-input-v1",
                                    source_artifact="canonical-context-input",
                                    source_sha256=fingerprint,
                                )
                                if fingerprint is not None
                                else None
                            ),
                        ),
                    ),
                ).clause
                updated.append(enriched_clause)
                enriched_ids.add(clause.id.value)
                state = "ok"
                outcome["status"] = "succeeded"

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
                        detail=failure_detail,
                    )
                )

        result = document.model_copy(update={"clauses": tuple(updated)})
        if result != original_document:
            self._documents.save(result)
        return ContextEnrichmentResult(
            routing_reused=reused,
            routing_outcomes=tuple(routing_outcomes),
            document=result,
            candidates=total,
            clauses_enriched=len(enriched_ids),
            subject_clauses=len(document.clauses),
            subjects_identified=subject_report.analysis.resolved_clauses,
            subjects_ambiguous=subject_report.analysis.ambiguous_clauses,
            context_enrichment_failures=failures,
            routing_failures=tuple(routing_failures),
            unresolved_scope_targets=_unresolved_scope_targets(result),
            unresolved_reference_targets=_unresolved_reference_targets(result),
            routing_corrections=tuple(routing_corrections),
        )


def _unresolved_scope_targets(document: EngineeringDocument) -> tuple[dict[str, object], ...]:
    """Report retained literal target groups separately from invalid generation.

    Include reused/protected state too: an unchanged value is not proof that its
    targets have become addressable. Evidence stays in this private report only.
    """
    return tuple(
        {
            "source_clause_id": scope.source_clause_id,
            "source_reference": clause.reference.as_text(),
            "scope_index": scope_index,
            "reach_index": reach_index,
            "document_key": reach.document_key or document.key.value,
            "kind": reach.kind.value,
            "reference": reach.reference,
            "clause_id": None,
            "status": "unresolved",
            "evidence": scope.evidence,
            "conditions": scope.conditions,
            "exclusions": scope.exclusions,
            "qualifications": scope.qualifications,
        }
        for clause in document.clauses
        for scope_index, scope in enumerate(clause.context_routing.scopes)
        for reach_index, reach in enumerate(scope.reaches)
        if reach.kind.value in {"clause", "subtree"} and reach.clause_id is None
    )


def _unresolved_reference_targets(document: EngineeringDocument) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "source_clause_id": edge.source_clause_id,
            "source_reference": clause.reference.as_text(),
            "reference_index": position,
            "document_key": edge.target.document_key,
            "reference": edge.target.reference,
            "clause_id": None,
            "status": "unresolved",
            "role": edge.role.value,
            "evidence": edge.evidence,
        }
        for clause in document.clauses
        for position, edge in enumerate(clause.context_routing.references)
        if edge.target.clause_id is None
    )


def _subject_context(result: ClauseSubjectIdentification) -> ClauseSubjectContext:
    primary = result.primary_subject
    ambiguous = tuple(result.ambiguous_candidates)
    if primary is None:
        return ClauseSubjectContext(ambiguous_candidates=ambiguous)
    evidence = primary.evidence
    return ClauseSubjectContext(
        primary_subject=PrimarySubjectContext(
            normalized_label=primary.normalized_label,
            confidence=primary.confidence,
            evidence=SubjectContextEvidence(
                kind=evidence.kind,
                matched_label=evidence.matched_label,
                source_text=evidence.source_text,
                source_clause_id=evidence.source_clause_id,
                ancestor_distance=evidence.ancestor_distance,
            ),
        ),
        ambiguous_candidates=ambiguous,
    )


def _source_evidence(clause: Clause) -> tuple[str, ...]:
    structural = clause.structural_context
    scope_evidence = (
        tuple(item.surface_text for item in structural.scope_mentions) if structural else ()
    )
    reference_evidence = tuple(item.surface_text for item in clause.reference_mentions)
    return tuple(dict.fromkeys((*scope_evidence, *reference_evidence)))
