import json

import pytest

from standards_atlas.adapters.llm import OntologyGuidedKnowledgeProposalExtractor
from standards_atlas.application.context import (
    ContextSelectionProfile,
    build_context_source_package,
    build_structured_context_candidates,
    select_structured_context,
)
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    EntityAssertionObject,
    EvidenceSourceKind,
    KnowledgeProposalViolationKind,
    NormativeForce,
    StandardReference,
    TextBlock,
)

STAT = "http://lunetix.org/standards-atlas#"
ONTOLOGIES = ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")


class _Gateway:
    def __init__(self, value: dict[str, object]) -> None:
        self.value = value
        self.request = None

    def generate_structured(self, request):
        self.request = request
        return StructuredGenerationResult(
            value=self.value,
            model="test-model",
            provider="test-provider",
            prompt_version=request.prompt_version,
            input_hash="a" * 64,
            raw_response_hash="b" * 64,
            duration_ms=4,
        )


def _document() -> tuple[EngineeringDocument, Clause]:
    parent = Clause(
        id=ClauseId(value="parent"),
        reference=StandardReference(standard="TEST", year=2026, clause="5"),
        clause_type=ClauseType.CLAUSE,
        heading="Safety plan confirmation review",
    )
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="TEST", year=2026, clause="5.1"),
        clause_type=ClauseType.REQUIREMENT,
        heading="Evaluation",
        parent_id=parent.id,
        content=(
            TextBlock(
                id="t-target",
                text="The evaluation shall assess the verification criteria.",
            ),
        ),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test standard",
        document_type=DocumentType.STANDARD,
        clauses=(parent, target),
    )
    return document, target


def _package(document: EngineeringDocument, target: Clause):
    inventory = build_structured_context_candidates(document, target)
    selection = select_structured_context(
        inventory,
        profile=ContextSelectionProfile(character_budget=20_000, max_sequence_distance=8),
    )
    return build_context_source_package(document, inventory, selection)


def _source_ref(package, clause_id: str, kind: EvidenceSourceKind) -> str:
    return next(
        surface.package_source_ref
        for surface in package.input_surfaces
        if surface.source_ref.clause_id == clause_id and surface.source_ref.source_kind is kind
    )


def _evidence(source_ref: str, quote: str, contribution: str = "direct_statement"):
    return [
        {
            "source_ref": source_ref,
            "exact_quote": quote,
            "selector": {"kind": "unique"},
            "contribution": contribution,
        }
    ]


def test_extractor_uses_bound_multi_source_evidence_lists_for_entities_and_assertions() -> None:
    document, target = _document()
    package = _package(document, target)
    parent_heading = _source_ref(package, "parent", EvidenceSourceKind.HEADING)
    target_body = _source_ref(package, "target", EvidenceSourceKind.BODY)
    statement = "The evaluation shall assess the verification criteria."
    gateway = _Gateway(
        {
            "entities": [
                {
                    "class_iri": f"{STAT}Activity",
                    "label": "safety plan confirmation review",
                    "confidence": 0.96,
                    "evidence": _evidence(
                        parent_heading,
                        "Safety plan confirmation review",
                        "subject_frame",
                    ),
                    "rationale": "parent heading supplies the review subject",
                },
                {
                    "class_iri": f"{STAT}VerificationCriterion",
                    "label": "verification criteria",
                    "confidence": 0.94,
                    "evidence": _evidence(target_body, "verification criteria"),
                    "rationale": None,
                },
            ],
            "assertions": [
                {
                    "subject_index": 0,
                    "predicate": f"{STAT}assesses",
                    "object_kind": "entity",
                    "object_index": 1,
                    "literal_value": None,
                    "literal_datatype_iri": None,
                    "literal_language": None,
                    "normative_force": "requirement",
                    "confidence": 0.93,
                    "evidence": [
                        {
                            "source_ref": parent_heading,
                            "exact_quote": "Safety plan confirmation review",
                            "selector": {"kind": "unique"},
                            "contribution": "subject_frame",
                        },
                        {
                            "source_ref": target_body,
                            "exact_quote": statement,
                            "selector": {"kind": "unique"},
                            "contribution": "direct_statement",
                        },
                    ],
                    "rationale": "the local statement is interpreted in the parent frame",
                }
            ],
        }
    )

    result = OntologyGuidedKnowledgeProposalExtractor(gateway).extract(
        target,
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
        source_package=package,
        interpretation_context={"normative_status": "normative"},
    )

    assert len(result.entity_proposals) == 2
    assert len(result.assertion_proposals) == 1
    assertion = result.assertion_proposals[0]
    assert assertion.normative_force is NormativeForce.REQUIREMENT
    assert assertion.predicate == f"{STAT}assesses"
    assert isinstance(assertion.object, EntityAssertionObject)
    assert len(assertion.evidence_anchor_ids) == 2
    anchors = {anchor.id: anchor for anchor in result.evidence_anchors}
    assert {anchors[item].source_clause_id.value for item in assertion.evidence_anchor_ids} == {
        "parent",
        "target",
    }
    assert result.source_package_binding is not None
    assert result.source_package_binding.target_clause_id == "target"
    assert result.proposal_provenance is not None
    assert (
        result.proposal_provenance.output_contract_id == "source-bound-knowledge-proposal-output-v1"
    )

    payload = json.loads(gateway.request.user_prompt)
    assert "clause_text" not in payload
    assert "clause_title" not in payload
    assert (
        payload["source_package"]["binding"]["package_sha256"]
        == result.source_package_binding.package_sha256
    )
    assert len(payload["source_package"]["source_surfaces"]) >= 3
    assert "Separate spans stay separate" in gateway.request.system_prompt


def test_extractor_does_not_silently_switch_declared_source_surface() -> None:
    document, target = _document()
    package = _package(document, target)
    target_body = _source_ref(package, "target", EvidenceSourceKind.BODY)
    gateway = _Gateway(
        {
            "entities": [
                {
                    "class_iri": f"{STAT}Activity",
                    "label": "safety plan confirmation review",
                    "confidence": 0.9,
                    # Quote exists in the parent heading, not in this declared target body.
                    "evidence": _evidence(target_body, "Safety plan confirmation review"),
                    "rationale": None,
                }
            ],
            "assertions": [],
        }
    )

    result = OntologyGuidedKnowledgeProposalExtractor(gateway).extract(
        target,
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
        source_package=package,
    )

    assert result.entity_proposals == ()
    assert result.evidence_anchors == ()
    assert result.violations[0].kind is KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING
    assert "quote_not_found" in result.violations[0].reason


def test_current_parser_clearly_rejects_legacy_single_quote_payload() -> None:
    document, target = _document()
    package = _package(document, target)
    gateway = _Gateway(
        {
            "entities": [
                {
                    "class_iri": f"{STAT}Activity",
                    "label": "evaluation",
                    "confidence": 0.9,
                    "evidence_source_kind": "body",
                    "evidence_source_clause_id": "target",
                    "evidence_quote": "evaluation",
                    "evidence": [
                        {
                            "source_ref": "target-body",
                            "exact_quote": "evaluation",
                            "selector": {"kind": "unique_quote"},
                            "contribution": "direct_statement",
                        }
                    ],
                    "rationale": None,
                }
            ],
            "assertions": [],
        }
    )

    with pytest.raises(ValueError, match="legacy single-quote proposal output"):
        OntologyGuidedKnowledgeProposalExtractor(gateway).extract(
            target,
            document_key="TEST",
            ontology_versions=ONTOLOGIES,
            source_package=package,
        )
