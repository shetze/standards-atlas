"""Structured LLM adapter for assertion-centred engineering knowledge proposals."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping

from standards_atlas.application.knowledge_proposal_extraction import (
    FormalOntologyVocabulary,
    display_clause_reference,
    ground_evidence_quote,
    project_clause_content,
)
from standards_atlas.application.ports.knowledge_proposals import ClauseKnowledgeProposalResult
from standards_atlas.application.ports.llm_gateway import LlmGateway, StructuredGenerationRequest
from standards_atlas.domain.model import (
    Clause,
    EntityAssertionObject,
    KnowledgeEntityProposal,
    KnowledgeProposalProvenance,
    KnowledgeProposalViolation,
    KnowledgeProposalViolationKind,
    LiteralAssertionObject,
    NormativeAssertionProposal,
    NormativeForce,
)

_NORMATIVE_FORCE_VALUES = tuple(item.value for item in NormativeForce)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entities", "assertions"],
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "class_iri",
                    "label",
                    "confidence",
                    "evidence_quote",
                    "rationale",
                ],
                "properties": {
                    "class_iri": {"type": "string"},
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_quote": {"type": "string"},
                    "rationale": {"type": ["string", "null"]},
                },
            },
        },
        "assertions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "subject_index",
                    "predicate",
                    "object_kind",
                    "object_index",
                    "literal_value",
                    "literal_datatype_iri",
                    "literal_language",
                    "normative_force",
                    "confidence",
                    "evidence_quote",
                    "rationale",
                ],
                "properties": {
                    "subject_index": {"type": "integer", "minimum": 0},
                    "predicate": {"type": "string"},
                    "object_kind": {"type": "string", "enum": ["entity", "literal"]},
                    "object_index": {"type": ["integer", "null"], "minimum": 0},
                    "literal_value": {"type": ["string", "number", "boolean", "null"]},
                    "literal_datatype_iri": {"type": ["string", "null"]},
                    "literal_language": {"type": ["string", "null"]},
                    "normative_force": {
                        "type": "string",
                        "enum": list(_NORMATIVE_FORCE_VALUES),
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_quote": {"type": "string"},
                    "rationale": {"type": ["string", "null"]},
                },
            },
        },
    },
}


class OntologyGuidedKnowledgeProposalExtractor:
    """Propose evidence-grounded entities and normative assertions from one clause."""

    def __init__(
        self,
        gateway: LlmGateway,
        *,
        model: str | None = None,
        provider: str | None = None,
        prompt_version: str = "ontology-guided-assertions-v1",
        extractor_version: str = "3.0.0",
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._provider = provider
        self._prompt_version = prompt_version
        self._extractor_version = extractor_version

    def provenance(self) -> KnowledgeProposalProvenance:
        return KnowledgeProposalProvenance(
            extractor="ontology-guided-llm",
            extractor_version=self._extractor_version,
            model=self._model,
            provider=self._provider,
            semantic_task="formal-semantic-knowledge-proposal",
            prompt_version=self._prompt_version,
        )

    def extract(
        self,
        clause: Clause,
        *,
        document_key: str,
        ontology_versions: tuple[str, ...],
        semantic_context: Mapping[str, object] | None = None,
    ) -> ClauseKnowledgeProposalResult:
        vocabulary = FormalOntologyVocabulary.load(ontology_versions)
        projection = project_clause_content(clause.content)
        request = StructuredGenerationRequest(
            task="formal-semantic-knowledge-proposal",
            prompt_version=self._prompt_version,
            model=self._model,
            temperature=0.0,
            output_schema=_SCHEMA,
            system_prompt=_system_prompt(),
            user_prompt=json.dumps(
                {
                    "document_key": document_key,
                    "clause_reference": display_clause_reference(document_key, clause.reference),
                    "clause_title": clause.heading,
                    "clause_id": clause.id.value,
                    "clause_text": projection.text,
                    "semantic_context": dict(semantic_context or {}),
                    "allowed_classes": sorted(vocabulary.classes),
                    "allowed_properties": sorted(vocabulary.properties),
                    "allowed_normative_force": list(_NORMATIVE_FORCE_VALUES),
                },
                ensure_ascii=False,
            ),
            metadata={"ontology_versions": ontology_versions},
        )
        result = self._gateway.generate_structured(request)
        payload = dict(result.value)

        anchors = {}
        entity_ids_by_index: list[str | None] = []
        entities: dict[str, KnowledgeEntityProposal] = {}
        violations: list[KnowledgeProposalViolation] = []

        for raw in payload.get("entities", []):
            class_iri = str(raw["class_iri"]).strip()
            label = str(raw["label"]).strip()
            if class_iri not in vocabulary.classes:
                violations.append(
                    _violation(
                        clause,
                        KnowledgeProposalViolationKind.UNDECLARED_CLASS,
                        class_iri,
                        "class is not source-extractable in the selected formal ontologies",
                    )
                )
                entity_ids_by_index.append(None)
                continue

            grounding = ground_evidence_quote(clause, str(raw["evidence_quote"]))
            if not grounding.resolved:
                assert grounding.violation_kind is not None
                violations.append(
                    _violation(
                        clause,
                        grounding.violation_kind,
                        str(raw["evidence_quote"]) or "<empty evidence>",
                        grounding.reason or "evidence grounding failed",
                    )
                )
                entity_ids_by_index.append(None)
                continue
            assert grounding.anchor is not None
            anchors[grounding.anchor.id] = grounding.anchor

            normalized_label = _normalize_entity_label(label)
            entity_id = _entity_id(
                document_key=document_key,
                clause_id=clause.id.value,
                normalized_label=normalized_label,
                class_iri=class_iri,
            )
            if entity_id in entities:
                violations.append(
                    _violation(
                        clause,
                        KnowledgeProposalViolationKind.DUPLICATE_ENTITY_ID,
                        entity_id,
                        "duplicate entity proposal resolves to an existing local entity id",
                    )
                )
                entity_ids_by_index.append(entity_id)
                continue

            entities[entity_id] = KnowledgeEntityProposal(
                id=entity_id,
                class_iri=class_iri,
                normalized_label=normalized_label,
                aliases=(label,) if label != normalized_label else (),
                source_anchor_ids=(grounding.anchor.id,),
                confidence=float(raw["confidence"]),
                rationale=_optional_text(raw.get("rationale")),
            )
            entity_ids_by_index.append(entity_id)

        assertions: list[NormativeAssertionProposal] = []
        assertion_ids: set[str] = set()
        for raw in payload.get("assertions", []):
            predicate = str(raw["predicate"]).strip()
            if predicate not in vocabulary.properties:
                violations.append(
                    _violation(
                        clause,
                        KnowledgeProposalViolationKind.UNDECLARED_PROPERTY,
                        predicate,
                        "property is not source-extractable in the selected formal ontologies",
                    )
                )
                continue

            subject_id = _entity_id_at(raw.get("subject_index"), entity_ids_by_index)
            if subject_id is None:
                violations.append(
                    _invalid_assertion(
                        clause,
                        predicate,
                        "assertion subject index is invalid or refers to a rejected entity",
                    )
                )
                continue
            try:
                object_ = _assertion_object(raw, entity_ids_by_index)
                normative_force = NormativeForce(str(raw["normative_force"]))
            except (TypeError, ValueError) as error:
                violations.append(_invalid_assertion(clause, predicate, str(error)))
                continue

            grounding = ground_evidence_quote(clause, str(raw["evidence_quote"]))
            if not grounding.resolved:
                assert grounding.violation_kind is not None
                violations.append(
                    _violation(
                        clause,
                        grounding.violation_kind,
                        str(raw["evidence_quote"]) or "<empty evidence>",
                        grounding.reason or "evidence grounding failed",
                    )
                )
                continue
            assert grounding.anchor is not None
            anchors[grounding.anchor.id] = grounding.anchor

            assertion_id = _assertion_id(
                document_key=document_key,
                clause_id=clause.id.value,
                subject_id=subject_id,
                predicate=predicate,
                object_payload=object_.model_dump(mode="json"),
                normative_force=normative_force,
                evidence_anchor_id=grounding.anchor.id,
            )
            if assertion_id in assertion_ids:
                violations.append(
                    _invalid_assertion(clause, assertion_id, "duplicate assertion proposal")
                )
                continue
            assertion_ids.add(assertion_id)
            try:
                assertion = NormativeAssertionProposal(
                    id=assertion_id,
                    source_clause_id=clause.id,
                    subject_id=subject_id,
                    predicate=predicate,
                    object=object_,
                    normative_force=normative_force,
                    evidence_anchor_ids=(grounding.anchor.id,),
                    confidence=float(raw["confidence"]),
                    rationale=_optional_text(raw.get("rationale")),
                )
            except ValueError as error:
                violations.append(_invalid_assertion(clause, predicate, str(error)))
                continue
            assertions.append(assertion)

        return ClauseKnowledgeProposalResult(
            clause_id=clause.id,
            evidence_anchors=tuple(anchors.values()),
            entity_proposals=tuple(entities.values()),
            assertion_proposals=tuple(assertions),
            violations=tuple(violations),
            proposal_provenance=KnowledgeProposalProvenance(
                extractor="ontology-guided-llm",
                extractor_version=self._extractor_version,
                model=result.model,
                provider=result.provider,
                semantic_task="formal-semantic-knowledge-proposal",
                prompt_version=result.prompt_version,
            ),
            input_hash=result.input_hash,
            raw_response_hash=result.raw_response_hash,
        )


def _system_prompt() -> str:
    return (
        "Extract engineering entities and normative assertions from the clause. "
        "semantic_context is trusted canonical CBox context for interpreting the clause: use its "
        "parent/ancestor structure, sibling position, governing scopes, normative_context and "
        "routed references to disambiguate the meaning of clause_text, but never emit an assertion "
        "from semantic_context alone. normative_context.effective_status is the default source "
        "force context for this clause: when it is informative, source-grounded assertions are "
        "informative even if the prose uses modal-looking wording. "
        "normative_context.span_overrides marks NOTE/EXAMPLE/DESCRIPTION-style source spans that "
        "are informative inside an otherwise normative clause. "
        "Evidence must always come from clause_text. "
        "allowed_classes and allowed_properties are closed vocabularies: copy their IRIs "
        "exactly and never invent semantic terms. Emit only claims directly supported by the "
        "source clause. Each evidence_quote MUST be an exact, case-sensitive, punctuation- and "
        "whitespace-preserving substring of clause_text and should be long enough to occur only "
        "once. Never use an omitted-table marker as evidence. Evidence quotes are source spans, "
        "not rationales; put explanatory text only in rationale. Assertions reference the ordered "
        "entities array by zero-based subject_index and, for entity objects, object_index. For a "
        "literal object set object_kind=literal, object_index=null and provide literal_value; for "
        "an entity object set object_kind=entity and literal fields to null. normative_force is "
        "assertion-local: requirement means mandatory positive duty, prohibition means mandatory "
        "negative duty, recommendation means advised but non-mandatory, permission means "
        "explicitly "
        "allowed, informative means descriptive context, and unspecified is used only when force "
        "cannot be determined from the assertion. Do not derive force solely from clause-level "
        "normative_status. Omit an entity or assertion when it cannot be grounded faithfully."
    )


def _assertion_object(
    raw: Mapping[str, object], entity_ids_by_index: list[str | None]
) -> EntityAssertionObject | LiteralAssertionObject:
    kind = str(raw["object_kind"])
    if kind == "entity":
        object_id = _entity_id_at(raw.get("object_index"), entity_ids_by_index)
        if object_id is None:
            raise ValueError(
                "entity assertion object index is invalid or refers to a rejected entity"
            )
        if any(
            raw.get(name) is not None
            for name in ("literal_value", "literal_datatype_iri", "literal_language")
        ):
            raise ValueError("entity assertion objects must not carry literal fields")
        return EntityAssertionObject(entity_id=object_id)
    if kind == "literal":
        if raw.get("object_index") is not None:
            raise ValueError("literal assertion objects must not carry object_index")
        value = raw.get("literal_value")
        if value is None:
            raise ValueError("literal assertion objects require literal_value")
        datatype = _optional_text(raw.get("literal_datatype_iri"))
        language = _optional_text(raw.get("literal_language"))
        return LiteralAssertionObject(value=value, datatype_iri=datatype, language=language)
    raise ValueError(f"unsupported assertion object kind: {kind!r}")


def _entity_id_at(index: object, entity_ids: list[str | None]) -> str | None:
    if type(index) is not int or not 0 <= index < len(entity_ids):
        return None
    return entity_ids[index]


def _entity_id(*, document_key: str, clause_id: str, normalized_label: str, class_iri: str) -> str:
    digest = hashlib.sha256(
        f"{document_key}|{clause_id}|{normalized_label}|{class_iri}".encode()
    ).hexdigest()[:20]
    return f"entity:{document_key}:{clause_id}:{digest}"


def _assertion_id(
    *,
    document_key: str,
    clause_id: str,
    subject_id: str,
    predicate: str,
    object_payload: Mapping[str, object],
    normative_force: NormativeForce,
    evidence_anchor_id: str,
) -> str:
    payload = json.dumps(
        {
            "document_key": document_key,
            "clause_id": clause_id,
            "subject_id": subject_id,
            "predicate": predicate,
            "object": object_payload,
            "normative_force": normative_force.value,
            "evidence_anchor_id": evidence_anchor_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"assertion:{document_key}:{clause_id}:{digest}"


def _normalize_entity_label(label: str) -> str:
    normalized = unicodedata.normalize("NFKC", label).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _violation(
    clause: Clause,
    kind: KnowledgeProposalViolationKind,
    term: str,
    reason: str,
) -> KnowledgeProposalViolation:
    return KnowledgeProposalViolation(
        clause_id=clause.id,
        kind=kind,
        term=term or "<empty>",
        reason=reason,
    )


def _invalid_assertion(clause: Clause, term: str, reason: str) -> KnowledgeProposalViolation:
    return _violation(
        clause,
        KnowledgeProposalViolationKind.INVALID_ASSERTION,
        term or "<assertion>",
        reason,
    )
