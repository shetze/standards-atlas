"""Independent source-bound LLM verifier for assertion proposals."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionCandidateVerification,
    AssertionClauseVerification,
    AssertionVerificationDisposition,
    AssertionVerifierProvenance,
)
from standards_atlas.application.context.input_binding import (
    ContextSourcePackage,
    context_source_package_binding,
)
from standards_atlas.application.knowledge_proposal_extraction import (
    FormalOntologyVocabulary,
    display_clause_reference,
)
from standards_atlas.application.knowledge_proposal_extraction.source_bound_contract import (
    ASSERTION_VERIFIER_REQUEST_CONTRACT,
    anchor_payload_from_source_package,
    source_package_request_payload,
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
    """Verify candidates against the same immutable source package used for extraction."""

    def __init__(
        self,
        gateway: LlmGateway,
        *,
        model: str | None = None,
        provider: str | None = None,
        prompt_version: str = "ontology-guided-assertion-verifier-source-bound-v1",
        verifier_version: str = "2.0.0",
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
            request_contract_id=ASSERTION_VERIFIER_REQUEST_CONTRACT,
            source_binding_contract_id="source-bound-context-binding-v1",
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
        source_package: ContextSourcePackage,
        interpretation_context: Mapping[str, object] | None = None,
    ) -> AssertionClauseVerification:
        if source_package.document_key != document_key:
            raise ValueError("verifier source package belongs to a different document")
        if source_package.target_clause_id != clause.id.value:
            raise ValueError("verifier source package belongs to a different target clause")
        vocabulary = FormalOntologyVocabulary.load(ontology_versions)
        binding = context_source_package_binding(source_package)
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
                    "request_contract_id": ASSERTION_VERIFIER_REQUEST_CONTRACT,
                    "document_key": document_key,
                    "target_clause": {
                        "clause_id": clause.id.value,
                        "reference": display_clause_reference(document_key, clause.reference),
                    },
                    "source_package": source_package_request_payload(source_package),
                    "interpretation_context": dict(interpretation_context or {}),
                    "allowed_classes": sorted(vocabulary.classes),
                    "allowed_properties": sorted(vocabulary.properties),
                    "entity_candidates": [
                        _entity_payload(item, anchor_by_id, source_package)
                        for item in entity_proposals
                    ],
                    "assertion_candidates": [
                        _assertion_payload(item, anchor_by_id, source_package)
                        for item in assertion_proposals
                    ],
                },
                ensure_ascii=False,
            ),
            metadata={
                "ontology_versions": ontology_versions,
                "source_package_sha256": binding.package_sha256,
                "request_contract_id": ASSERTION_VERIFIER_REQUEST_CONTRACT,
            },
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
            source_package_sha256=binding.package_sha256,
        )
        _validate_candidate_ids(
            verification,
            entity_ids={item.id for item in entity_proposals},
            assertion_ids={item.id for item in assertion_proposals},
        )
        return verification


def _system_prompt() -> str:
    return (
        "Act as an independent verifier of engineering-knowledge candidates for target_clause. "
        "Use only the exact text in source_package.source_surfaces; interpretation_context is "
        "source-free metadata and is not evidence. Candidate evidence may contain several spans "
        "from local or context body/heading surfaces. Verify the declared source ownership, the "
        "meaning of every span, the combined claim, conditions/exceptions, direction, predicate "
        "and "
        "normative force. A context passage being supplied does not prove that its meaning applies "
        "to the target; unclear semantic reach is uncertainty, not automatic support. Do not "
        "demand "
        "mechanical extraction of every note, example, mention or list item. Review every supplied "
        "candidate exactly once. Then inspect the complete supplied package for important omitted "
        "source-extractable entities/assertions, while respecting selection gaps and incomplete "
        "context. Do not silently use document text outside the bound package, repair candidates, "
        "or invent replacement assertions."
    )


def _entity_payload(
    entity: KnowledgeEntityProposal,
    anchor_by_id: Mapping[str, EvidenceAnchor],
    package: ContextSourcePackage,
) -> dict[str, object]:
    return {
        "candidate_id": entity.id,
        "class_iri": entity.class_iri,
        "normalized_label": entity.normalized_label,
        "aliases": list(entity.aliases),
        "confidence": entity.confidence,
        "evidence": [
            anchor_payload_from_source_package(anchor_by_id[anchor_id], package)
            for anchor_id in entity.source_anchor_ids
        ],
    }


def _assertion_payload(
    assertion: NormativeAssertionProposal,
    anchor_by_id: Mapping[str, EvidenceAnchor],
    package: ContextSourcePackage,
) -> dict[str, object]:
    return {
        "candidate_id": assertion.id,
        "source_clause_id": assertion.source_clause_id.value,
        "subject_id": assertion.subject_id,
        "predicate": assertion.predicate,
        "object": assertion.object.model_dump(mode="json"),
        "normative_force": assertion.normative_force.value,
        "confidence": assertion.confidence,
        "evidence": [
            anchor_payload_from_source_package(anchor_by_id[anchor_id], package)
            for anchor_id in assertion.evidence_anchor_ids
        ],
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
