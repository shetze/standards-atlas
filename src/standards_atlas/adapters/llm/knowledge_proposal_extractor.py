"""Structured LLM adapter for source-bound assertion-centred knowledge proposals."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping

from standards_atlas.application.context.input_binding import (
    ContextSourcePackage,
    context_source_package_binding,
)
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.evaluation.source_bound_prompt import (
    build_source_bound_generation_request,
    semantic_prompt_repository,
)
from standards_atlas.application.knowledge_proposal_extraction import (
    EvidenceGroundingFailureCode,
    EvidenceGroundingOwnerKind,
    EvidenceGroundingRequest,
    EvidenceUse,
    FormalOntologyVocabulary,
    display_clause_reference,
    ground_evidence_request,
)
from standards_atlas.application.knowledge_proposal_extraction.source_bound_contract import (
    KNOWLEDGE_PROPOSAL_OUTPUT_CONTRACT,
    KNOWLEDGE_PROPOSAL_REQUEST_CONTRACT,
    source_package_request_payload,
)
from standards_atlas.application.ports.knowledge_proposals import ClauseKnowledgeProposalResult
from standards_atlas.application.ports.llm_gateway import LlmGateway
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


class OntologyGuidedKnowledgeProposalExtractor:
    """Propose source-bound entities and assertions from one target clause."""

    def __init__(
        self,
        gateway: LlmGateway,
        *,
        model: str | None = None,
        provider: str | None = None,
        prompt_version: str = "ontology-guided-assertions-source-bound-v1",
        task_schema_version: str = "1.0.0",
        extractor_version: str = "4.0.0",
        prompt_repository: PromptRepository | None = None,
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._provider = provider
        self._prompt_version = prompt_version
        self._task_schema_version = task_schema_version
        self._extractor_version = extractor_version
        self._prompt_repository = prompt_repository or semantic_prompt_repository()

    def provenance(self) -> KnowledgeProposalProvenance:
        return KnowledgeProposalProvenance(
            extractor="ontology-guided-llm",
            extractor_version=self._extractor_version,
            model=self._model,
            provider=self._provider,
            semantic_task="formal-semantic-knowledge-proposal",
            prompt_version=self._prompt_version,
            request_contract_id=KNOWLEDGE_PROPOSAL_REQUEST_CONTRACT,
            output_contract_id=KNOWLEDGE_PROPOSAL_OUTPUT_CONTRACT,
            source_binding_contract_id="source-bound-context-binding-v1",
        )

    def extract(
        self,
        clause: Clause,
        *,
        document_key: str,
        ontology_versions: tuple[str, ...],
        source_package: ContextSourcePackage,
        interpretation_context: Mapping[str, object] | None = None,
    ) -> ClauseKnowledgeProposalResult:
        if source_package.document_key != document_key:
            raise ValueError("extractor source package belongs to a different document")
        if source_package.target_clause_id != clause.id.value:
            raise ValueError("extractor source package belongs to a different target clause")

        vocabulary = FormalOntologyVocabulary.load(ontology_versions)
        binding = context_source_package_binding(source_package)
        request_payload = {
            "request_contract_id": KNOWLEDGE_PROPOSAL_REQUEST_CONTRACT,
            "output_contract_id": KNOWLEDGE_PROPOSAL_OUTPUT_CONTRACT,
            "document_key": document_key,
            "target_clause": {
                "clause_id": clause.id.value,
                "reference": display_clause_reference(document_key, clause.reference),
            },
            "source_package": source_package_request_payload(source_package),
            "interpretation_context": dict(interpretation_context or {}),
            "allowed_classes": sorted(vocabulary.classes),
            "allowed_properties": sorted(vocabulary.properties),
            "allowed_normative_force": list(_NORMATIVE_FORCE_VALUES),
        }
        request = build_source_bound_generation_request(
            repository=self._prompt_repository,
            task="formal-semantic-knowledge-proposal",
            prompt_version=self._prompt_version,
            task_schema_version=self._task_schema_version,
            payload=request_payload,
            model=self._model,
            temperature=0.0,
            metadata={
                "ontology_versions": ontology_versions,
                "source_package_sha256": binding.package_sha256,
                "request_contract_id": KNOWLEDGE_PROPOSAL_REQUEST_CONTRACT,
            },
        )
        result = self._gateway.generate_structured(request)
        payload = dict(result.value)
        _reject_legacy_single_quote_payload(payload)

        anchors = {}
        entity_ids_by_index: list[str | None] = []
        entities: dict[str, KnowledgeEntityProposal] = {}
        violations: list[KnowledgeProposalViolation] = []

        for entity_index, raw_object in enumerate(payload.get("entities", [])):
            if not isinstance(raw_object, Mapping):
                raise ValueError("knowledge proposal entity must be an object")
            raw = raw_object
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

            grounded, grounding_violations = _ground_payload_evidence(
                clause,
                raw,
                package=source_package,
                owner_kind=EvidenceGroundingOwnerKind.ENTITY,
                owner_id=f"entity[{entity_index}]",
            )
            violations.extend(grounding_violations)
            if grounded is None:
                entity_ids_by_index.append(None)
                continue
            for anchor in grounded:
                anchors[anchor.id] = anchor

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
                proposal_clause_ids=(clause.id,),
                class_iri=class_iri,
                normalized_label=normalized_label,
                aliases=(label,) if label != normalized_label else (),
                source_anchor_ids=tuple(anchor.id for anchor in grounded),
                confidence=float(raw["confidence"]),
                rationale=_optional_text(raw.get("rationale")),
            )
            entity_ids_by_index.append(entity_id)

        assertions: list[NormativeAssertionProposal] = []
        assertion_ids: set[str] = set()
        for assertion_index, raw_object in enumerate(payload.get("assertions", [])):
            if not isinstance(raw_object, Mapping):
                raise ValueError("knowledge proposal assertion must be an object")
            raw = raw_object
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

            grounded, grounding_violations = _ground_payload_evidence(
                clause,
                raw,
                package=source_package,
                owner_kind=EvidenceGroundingOwnerKind.ASSERTION,
                owner_id=f"assertion[{assertion_index}]",
            )
            violations.extend(grounding_violations)
            if grounded is None:
                continue
            for anchor in grounded:
                anchors[anchor.id] = anchor

            evidence_anchor_ids = tuple(anchor.id for anchor in grounded)
            assertion_id = _assertion_id(
                document_key=document_key,
                clause_id=clause.id.value,
                subject_id=subject_id,
                predicate=predicate,
                object_payload=object_.model_dump(mode="json"),
                normative_force=normative_force,
                evidence_anchor_ids=evidence_anchor_ids,
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
                    evidence_anchor_ids=evidence_anchor_ids,
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
            source_package_binding=binding,
            proposal_provenance=KnowledgeProposalProvenance(
                extractor="ontology-guided-llm",
                extractor_version=self._extractor_version,
                model=result.model,
                provider=result.provider,
                semantic_task="formal-semantic-knowledge-proposal",
                prompt_version=result.prompt_version,
                request_contract_id=KNOWLEDGE_PROPOSAL_REQUEST_CONTRACT,
                output_contract_id=KNOWLEDGE_PROPOSAL_OUTPUT_CONTRACT,
                source_binding_contract_id=binding.contract_id,
            ),
            input_hash=result.input_hash,
            raw_response_hash=result.raw_response_hash,
        )


def _reject_legacy_single_quote_payload(payload: Mapping[str, object]) -> None:
    legacy_fields = {"evidence_quote", "evidence_source_kind", "evidence_source_clause_id"}
    for collection_name in ("entities", "assertions"):
        values = payload.get(collection_name, [])
        if not isinstance(values, list):
            raise ValueError(f"knowledge proposal {collection_name} must be an array")
        for item in values:
            if isinstance(item, Mapping) and legacy_fields.intersection(item):
                raise ValueError(
                    "legacy single-quote proposal output is not accepted by the current "
                    "source-bound parser"
                )


def _ground_payload_evidence(
    clause: Clause,
    raw: Mapping[str, object],
    *,
    package: ContextSourcePackage,
    owner_kind: EvidenceGroundingOwnerKind,
    owner_id: str,
) -> tuple[tuple[object, ...] | None, tuple[KnowledgeProposalViolation, ...]]:
    raw_evidence = raw.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        return None, (
            _violation(
                clause,
                KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING,
                owner_id,
                "current source-bound proposal output requires a non-empty evidence list",
            ),
        )
    try:
        evidence = tuple(EvidenceUse.model_validate(item) for item in raw_evidence)
    except ValueError as error:
        return None, (
            _violation(
                clause,
                KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING,
                owner_id,
                f"invalid source-bound evidence declaration: {error}",
            ),
        )
    grounding = ground_evidence_request(
        package,
        EvidenceGroundingRequest(owner_kind=owner_kind, owner_id=owner_id, evidence=evidence),
    )
    if grounding.complete:
        return grounding.anchors, ()
    violations = []
    for failure in grounding.failures:
        kind = (
            KnowledgeProposalViolationKind.AMBIGUOUS_GROUNDING
            if failure.code is EvidenceGroundingFailureCode.AMBIGUOUS_QUOTE
            else KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING
        )
        violations.append(
            _violation(
                clause,
                kind,
                f"{owner_id}:evidence[{failure.use_index}]",
                f"{failure.code.value}: {failure.reason}",
            )
        )
    return None, tuple(violations)


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
    evidence_anchor_ids: tuple[str, ...],
) -> str:
    payload = json.dumps(
        {
            "document_key": document_key,
            "clause_id": clause_id,
            "subject_id": subject_id,
            "predicate": predicate,
            "object": object_payload,
            "normative_force": normative_force.value,
            "evidence_anchor_ids": list(evidence_anchor_ids),
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
