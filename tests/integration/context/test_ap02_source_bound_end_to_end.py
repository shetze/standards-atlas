from __future__ import annotations

import hashlib
import json
from pathlib import Path

from standards_atlas.adapters.filesystem import (
    FileSystemContextSourcePackageRepository,
    FileSystemDocumentKnowledgeProposalRepository,
    FileSystemEngineeringDocumentRepository,
    FileSystemFormalSemanticProjectionRepository,
)
from standards_atlas.adapters.llm import (
    OntologyGuidedAssertionProposalVerifier,
    OntologyGuidedKnowledgeProposalExtractor,
)
from standards_atlas.application.assertion_qualification import (
    AssertionAuditBinding,
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    AssertionQualificationCascadeService,
    AssertionQualificationEvaluator,
    GoldenEvidenceSpan,
    GoldenKnowledgeEntity,
    GoldenNormativeAssertion,
)
from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionCascadeRoute,
)
from standards_atlas.application.context import ContextSelectionProfile
from standards_atlas.application.context.input_binding import context_source_package_binding
from standards_atlas.application.formal_semantics import (
    DeterministicFormalSemanticProjector,
    FormalEvidenceResolutionStatus,
    FormalProjectionEvidenceResolver,
)
from standards_atlas.application.knowledge_proposal_extraction import (
    ProposalExtractionContext,
    assertion_context_source_package,
)
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.domain.model import (
    DocumentKey,
    DocumentKnowledge,
    EntityAssertionObject,
    EvidenceSourceKind,
    KnowledgeDerivationMethod,
    KnowledgeEntity,
    KnowledgeProvenance,
    NormativeAssertion,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_WORKSPACE = ROOT / "tests/fixtures/ap02/context-evidence-inspection/workspace"
ONTOLOGIES = ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")
STAT = "http://lunetix.org/standards-atlas#"
TARGET_BODY = "The evaluation shall assess the verification criteria and record the result."
PARENT_HEADING = "Safety plan confirmation review"


class _ExtractorGateway:
    """Deterministic fake adapter response; it never connects to a model server."""

    calls = 0

    def generate_structured(self, request):
        self.calls += 1
        payload = json.loads(request.user_prompt)
        surfaces = payload["source_package"]["source_surfaces"]

        def source_ref(clause_id: str, source_kind: str) -> str:
            return next(
                item["source_ref"]
                for item in surfaces
                if item["clause_id"] == clause_id and item["source_kind"] == source_kind
            )

        parent_heading = source_ref("parent", "heading")
        target_body = source_ref("target", "body")
        value = {
            "entities": [
                {
                    "class_iri": f"{STAT}Activity",
                    "label": "safety plan confirmation review",
                    "confidence": 0.97,
                    "evidence": [
                        {
                            "source_ref": parent_heading,
                            "exact_quote": PARENT_HEADING,
                            "selector": {"kind": "unique"},
                            "contribution": "subject_frame",
                        }
                    ],
                    "rationale": "synthetic parent heading frames the activity",
                },
                {
                    "class_iri": f"{STAT}VerificationCriterion",
                    "label": "verification criteria",
                    "confidence": 0.95,
                    "evidence": [
                        {
                            "source_ref": target_body,
                            "exact_quote": "verification criteria",
                            "selector": {"kind": "unique"},
                            "contribution": "direct_statement",
                        }
                    ],
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
                    "confidence": 0.94,
                    "evidence": [
                        {
                            "source_ref": parent_heading,
                            "exact_quote": PARENT_HEADING,
                            "selector": {"kind": "unique"},
                            "contribution": "subject_frame",
                        },
                        {
                            "source_ref": target_body,
                            "exact_quote": TARGET_BODY,
                            "selector": {"kind": "unique"},
                            "contribution": "direct_statement",
                        },
                    ],
                    "rationale": "synthetic multi-source relation",
                }
            ],
        }
        return _result(request, value, marker="extractor")


class _VerifierGateway:
    """Returns supported reviews for exactly the candidates in the request."""

    calls = 0

    def generate_structured(self, request):
        self.calls += 1
        payload = json.loads(request.user_prompt)
        value = {
            "entity_reviews": [
                {
                    "candidate_id": item["candidate_id"],
                    "disposition": "supported",
                    "rationale": None,
                }
                for item in payload["entity_candidates"]
            ],
            "assertion_reviews": [
                {
                    "candidate_id": item["candidate_id"],
                    "disposition": "supported",
                    "rationale": None,
                }
                for item in payload["assertion_candidates"]
            ],
            "missing_entity_detected": False,
            "missing_assertion_detected": False,
            "missing_rationale": None,
        }
        return _result(request, value, marker="verifier")


def _result(request, value: dict[str, object], *, marker: str) -> StructuredGenerationResult:
    input_hash = hashlib.sha256(request.user_prompt.encode("utf-8")).hexdigest()
    response_hash = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return StructuredGenerationResult(
        value=value,
        model=f"fake-{marker}",
        provider="synthetic-test",
        prompt_version=request.prompt_version,
        input_hash=input_hash,
        raw_response_hash=response_hash,
        duration_ms=0,
    )


def _golden_for(document, proposal) -> AssertionGoldenSuite:
    target = next(item for item in document.clauses if item.id.value == "target")
    review_entity = next(
        item
        for item in proposal.entity_proposals
        if item.normalized_label == "safety plan confirmation review"
    )
    criteria_entity = next(
        item
        for item in proposal.entity_proposals
        if item.normalized_label == "verification criteria"
    )
    candidate_assertion = proposal.assertion_proposals[0]
    anchors = {item.id: item for item in proposal.evidence_anchors}
    spans = tuple(
        GoldenEvidenceSpan(
            source_document_key=document.key.value,
            clause_id=anchors[anchor_id].source_clause_id,
            source_kind=anchors[anchor_id].source_kind,
            start_offset=anchors[anchor_id].start_offset,
            end_offset=anchors[anchor_id].end_offset,
            content_hash=anchors[anchor_id].content_hash,
        )
        for anchor_id in candidate_assertion.evidence_anchor_ids
    )
    assert all(item.start_offset is not None and item.end_offset is not None for item in spans)
    return AssertionGoldenSuite(
        id="ap02-series-f-synthetic",
        version="1.0.0",
        partition=AssertionGoldenPartition.DEVELOPMENT,
        audit=AssertionAuditBinding(
            review_id="synthetic-ap02-series-f",
            review_version="1",
            audit_sha256="0" * 64,
        ),
        ontology_versions=ONTOLOGIES,
        cases=(
            AssertionGoldenCase(
                source_document_key=document.key.value,
                clause_id=target.id,
                reference="AP02-SYNTH:5.2",
                canonical_reference="AP02-SYNTH 5.2",
                text_sha256=hashlib.sha256(target.plain_text.encode("utf-8")).hexdigest(),
                source_sha256="1" * 64,
                entities=(
                    GoldenKnowledgeEntity(
                        id="golden-review",
                        class_iri=review_entity.class_iri,
                        normalized_label="safety plan confirmation review",
                    ),
                    GoldenKnowledgeEntity(
                        id="golden-criteria",
                        class_iri=criteria_entity.class_iri,
                        normalized_label="verification criteria",
                    ),
                ),
                assertions=(
                    GoldenNormativeAssertion(
                        id="golden-assessment",
                        source_clause_id=target.id,
                        subject_id="golden-review",
                        predicate=candidate_assertion.predicate,
                        object=EntityAssertionObject(entity_id="golden-criteria"),
                        normative_force=candidate_assertion.normative_force,
                        evidence=spans,
                    ),
                ),
            ),
        ),
    )


def _synthetic_accepted_document(document, proposal):
    provenance = KnowledgeProvenance(
        method=KnowledgeDerivationMethod.HUMAN_AUTHORED,
        producer="ap02-series-f-synthetic-test",
        producer_version="1",
        review_reference="synthetic-only:no-adoption",
    )
    knowledge = DocumentKnowledge(
        ontology_versions=proposal.ontology_versions,
        evidence_anchors=proposal.evidence_anchors,
        entities=tuple(
            KnowledgeEntity(
                id=item.id,
                class_iri=item.class_iri,
                normalized_label=item.normalized_label,
                aliases=item.aliases,
                source_anchor_ids=item.source_anchor_ids,
            )
            for item in proposal.entity_proposals
        ),
        assertions=tuple(
            NormativeAssertion(
                id=item.id,
                source_clause_id=item.source_clause_id,
                subject_id=item.subject_id,
                predicate=item.predicate,
                object=item.object,
                normative_force=item.normative_force,
                evidence_anchor_ids=item.evidence_anchor_ids,
                provenance=provenance,
            )
            for item in proposal.assertion_proposals
        ),
    )
    return document.model_copy(update={"knowledge": knowledge})


def test_source_bound_pipeline_closes_from_selection_through_projection_without_real_models(
    tmp_path: Path,
) -> None:
    document = FileSystemEngineeringDocumentRepository(FIXTURE_WORKSPACE).load(
        DocumentKey(value="AP02-SYNTH")
    )
    target = next(item for item in document.clauses if item.id.value == "target")
    package = assertion_context_source_package(
        document,
        target,
        profile=ContextSelectionProfile(character_budget=20_000, max_sequence_distance=8),
    )
    assert any(item.source_ref.clause_id == "later" for item in package.input_surfaces)
    assert package.selection.completeness.value == "bounded"

    extractor_gateway = _ExtractorGateway()
    verifier_gateway = _VerifierGateway()
    cascade = AssertionQualificationCascadeService(
        efficient_extractor=OntologyGuidedKnowledgeProposalExtractor(extractor_gateway),
        verifier=OntologyGuidedAssertionProposalVerifier(verifier_gateway),
        escalation_extractor=OntologyGuidedKnowledgeProposalExtractor(_ExtractorGateway()),
    ).run_document(
        document,
        cascade_run_id="ap02-series-f-cascade",
        efficient_proposal_run_id="ap02-series-f-efficient",
        escalation_proposal_run_id="ap02-series-f-escalation",
        ontology_versions=ONTOLOGIES,
        clause_ids=frozenset({"target"}),
        context_by_clause={"target": ProposalExtractionContext(source_package=package)},
    )

    assert extractor_gateway.calls == 1
    assert verifier_gateway.calls == 1
    assert cascade.escalation_proposal is None
    assert cascade.report.clauses[0].route is AssertionCascadeRoute.EFFICIENT_ACCEPTED
    proposal = cascade.efficient_proposal
    assert len(proposal.evidence_anchors) == 3
    assert {item.source_clause_id.value for item in proposal.evidence_anchors} == {
        "parent",
        "target",
    }
    assert context_source_package_binding(package) in proposal.context_source_bindings

    packages = FileSystemContextSourcePackageRepository(tmp_path)
    package_binding = packages.save(package)
    proposals = FileSystemDocumentKnowledgeProposalRepository(tmp_path)
    proposals.save(proposal)
    reloaded_proposal = proposals.load(proposal.proposal_run_id, proposal.source_document_key)
    assert reloaded_proposal is not None
    reloaded_package = packages.load(package_binding)
    assert reloaded_package == package
    assert package_binding in reloaded_proposal.context_source_bindings

    golden = _golden_for(document, reloaded_proposal)
    evaluation = AssertionQualificationEvaluator().evaluate(
        golden,
        (reloaded_proposal,),
        source_packages=(reloaded_package,),
    )
    assert evaluation.source_binding == "native_package_verified"
    assert evaluation.aggregate.entities.f1.value == 1.0
    assert evaluation.aggregate.assertions.f1.value == 1.0
    assert evaluation.aggregate.evidence_integrity.validity.value == 1.0
    assert evaluation.aggregate.evidence_span_exact_match.accuracy.value == 1.0
    assert evaluation.aggregate.clause_exact_match.accuracy.value == 1.0
    assert evaluation.aggregate.semantic_evidence.status == "not_evaluated"

    accepted = _synthetic_accepted_document(document, reloaded_proposal)
    documents = FileSystemEngineeringDocumentRepository(tmp_path)
    documents.save(accepted)
    reloaded_document = documents.load(accepted.key)
    projection = DeterministicFormalSemanticProjector().project(reloaded_document)
    projections = FileSystemFormalSemanticProjectionRepository(tmp_path)
    projections.save(projection)
    reloaded_projection = projections.load(accepted.key.value)
    assert reloaded_projection is not None

    relation = next(
        item for item in reloaded_projection.assertions if item.predicate.iri == f"{STAT}assesses"
    )
    resolutions = FormalProjectionEvidenceResolver(
        reloaded_document, reloaded_projection
    ).resolve_assertion_evidence(relation)
    assert len(resolutions) == 2
    assert all(item.status is FormalEvidenceResolutionStatus.RESOLVED for item in resolutions)
    assert {item.anchor.source_kind for item in resolutions if item.anchor is not None} == {
        EvidenceSourceKind.HEADING,
        EvidenceSourceKind.BODY,
    }
    resolved_clause_ids = {
        item.anchor.source_clause_id.value for item in resolutions if item.anchor is not None
    }
    assert resolved_clause_ids == {
        "parent",
        "target",
    }
