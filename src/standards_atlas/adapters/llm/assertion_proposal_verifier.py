"""Independent ontology-aware LLM verifier for efficient assertion proposals."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionCandidateVerification,
    AssertionClauseVerification,
    AssertionVerificationDisposition,
    AssertionVerifierProvenance,
)
from standards_atlas.application.knowledge_proposal_extraction import (
    FormalOntologyVocabulary,
    display_clause_reference,
    project_clause_content,
)
from standards_atlas.application.ports.llm_gateway import LlmGateway, StructuredGenerationRequest
from standards_atlas.domain.model import (
    Clause,
    EvidenceAnchor,
    KnowledgeEntityProposal,
    NormativeAssertionProposal,
)

_DISPOSITIONS = [item.value for item in AssertionVerificationDisposition]
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "entity_reviews",
        "assertion_reviews",
        "missing_entity_detected",
        "missing_assertion_detected",
        "missing_rationale",
    ],
    "properties": {
        "entity_reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["candidate_id", "disposition", "rationale"],
                "properties": {
                    "candidate_id": {"type": "string"},
                    "disposition": {"type": "string", "enum": _DISPOSITIONS},
                    "rationale": {"type": ["string", "null"]},
                },
            },
        },
        "assertion_reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["candidate_id", "disposition", "rationale"],
                "properties": {
                    "candidate_id": {"type": "string"},
                    "disposition": {"type": "string", "enum": _DISPOSITIONS},
                    "rationale": {"type": ["string", "null"]},
                },
            },
        },
        "missing_entity_detected": {"type": "boolean"},
        "missing_assertion_detected": {"type": "boolean"},
        "missing_rationale": {"type": ["string", "null"]},
    },
}


class OntologyGuidedAssertionProposalVerifier:
    """Verify candidates independently and actively search for omitted assertions."""

    def __init__(
        self,
        gateway: LlmGateway,
        *,
        model: str | None = None,
        provider: str | None = None,
        prompt_version: str = "ontology-guided-assertion-verifier-v1",
        verifier_version: str = "1.0.0",
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._provider = provider
        self._prompt_version = prompt_version
        self._verifier_version = verifier_version

    def provenance(self) -> AssertionVerifierProvenance:
        return AssertionVerifierProvenance(
            verifier="ontology-guided-llm-verifier",
            verifier_version=self._verifier_version,
            model=self._model,
            provider=self._provider,
            prompt_version=self._prompt_version,
        )

    def verify(
        self,
        clause: Clause,
        *,
        document_key: str,
        ontology_versions: tuple[str, ...],
        evidence_anchors: Sequence[EvidenceAnchor],
        entity_proposals: Sequence[KnowledgeEntityProposal],
        assertion_proposals: Sequence[NormativeAssertionProposal],
        semantic_context: Mapping[str, object] | None = None,
    ) -> AssertionClauseVerification:
        vocabulary = FormalOntologyVocabulary.load(ontology_versions)
        projection = project_clause_content(clause.content)
        anchor_by_id = {anchor.id: anchor for anchor in evidence_anchors}
        request = StructuredGenerationRequest(
            task="formal-semantic-assertion-verification",
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
                    "entity_candidates": [
                        _entity_payload(item, anchor_by_id, clause) for item in entity_proposals
                    ],
                    "assertion_candidates": [
                        _assertion_payload(item, anchor_by_id, clause)
                        for item in assertion_proposals
                    ],
                },
                ensure_ascii=False,
            ),
            metadata={"ontology_versions": ontology_versions},
        )
        result = self._gateway.generate_structured(request)
        payload = dict(result.value)
        verification = AssertionClauseVerification(
            clause_id=clause.id,
            entity_reviews=tuple(_review(item) for item in payload.get("entity_reviews", [])),
            assertion_reviews=tuple(_review(item) for item in payload.get("assertion_reviews", [])),
            missing_entity_detected=bool(payload["missing_entity_detected"]),
            missing_assertion_detected=bool(payload["missing_assertion_detected"]),
            missing_rationale=_optional_text(payload.get("missing_rationale")),
            input_hash=result.input_hash,
            raw_response_hash=result.raw_response_hash,
        )
        _validate_candidate_ids(
            verification,
            entity_ids={item.id for item in entity_proposals},
            assertion_ids={item.id for item in assertion_proposals},
        )
        return verification


def _system_prompt() -> str:
    return (
        "Act as an independent verifier of engineering-knowledge candidates extracted from one "
        "standards clause. Review every supplied entity and assertion exactly once. Mark a "
        "candidate supported only when its semantics and cited source evidence are directly "
        "supported by clause_text. Mark it rejected when it is contradicted, invented, uses the "
        "wrong ontology meaning, or overstates the source. Use uncertain when the source does not "
        "permit a reliable decision. Then independently inspect the complete clause for important "
        "source-extractable engineering entities or assertions omitted by the efficient stage; "
        "this missing-item check is mandatory even when the candidate arrays are empty. Set the "
        "missing flags only for semantics expressible with allowed_classes/allowed_properties. "
        "Do not repair candidates and do not propose replacement assertions."
    )


def _entity_payload(
    entity: KnowledgeEntityProposal,
    anchor_by_id: Mapping[str, EvidenceAnchor],
    clause: Clause,
) -> dict[str, object]:
    return {
        "candidate_id": entity.id,
        "class_iri": entity.class_iri,
        "normalized_label": entity.normalized_label,
        "aliases": list(entity.aliases),
        "confidence": entity.confidence,
        "evidence": [
            _anchor_payload(anchor_by_id[anchor_id], clause)
            for anchor_id in entity.source_anchor_ids
        ],
    }


def _assertion_payload(
    assertion: NormativeAssertionProposal,
    anchor_by_id: Mapping[str, EvidenceAnchor],
    clause: Clause,
) -> dict[str, object]:
    return {
        "candidate_id": assertion.id,
        "subject_id": assertion.subject_id,
        "predicate": assertion.predicate,
        "object": assertion.object.model_dump(mode="json"),
        "normative_force": assertion.normative_force.value,
        "confidence": assertion.confidence,
        "evidence": [
            _anchor_payload(anchor_by_id[anchor_id], clause)
            for anchor_id in assertion.evidence_anchor_ids
        ],
    }


def _anchor_payload(anchor: EvidenceAnchor, clause: Clause) -> dict[str, object]:
    if anchor.clause_id != clause.id:
        raise ValueError("assertion verifier received evidence from a different source clause")
    if anchor.start_offset is None or anchor.end_offset is None:
        quote = clause.plain_text
    else:
        quote = clause.plain_text[anchor.start_offset : anchor.end_offset]
    return {
        "anchor_id": anchor.id,
        "start_offset": anchor.start_offset,
        "end_offset": anchor.end_offset,
        "content_hash": anchor.content_hash,
        "quote": quote,
    }


def _review(payload: object) -> AssertionCandidateVerification:
    if not isinstance(payload, Mapping):
        raise ValueError("assertion verifier review must be a mapping")
    return AssertionCandidateVerification(
        candidate_id=str(payload["candidate_id"]),
        disposition=AssertionVerificationDisposition(str(payload["disposition"])),
        rationale=_optional_text(payload.get("rationale")),
    )


def _validate_candidate_ids(
    verification: AssertionClauseVerification,
    *,
    entity_ids: set[str],
    assertion_ids: set[str],
) -> None:
    if {item.candidate_id for item in verification.entity_reviews} != entity_ids:
        raise ValueError("assertion verifier must return exactly the supplied entity candidate ids")
    if {item.candidate_id for item in verification.assertion_reviews} != assertion_ids:
        raise ValueError(
            "assertion verifier must return exactly the supplied assertion candidate ids"
        )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
