import hashlib

import pytest

from standards_atlas.domain.model import (
    ClauseId,
    DocumentKnowledgeProposal,
    EntityAssertionObject,
    EvidenceAnchor,
    EvidenceSourceKind,
    KnowledgeEntity,
    KnowledgeEntityProposal,
    KnowledgeProposalAttempt,
    KnowledgeProposalFailure,
    KnowledgeProposalInput,
    KnowledgeProposalProvenance,
    KnowledgeProposalViolation,
    NormativeAssertion,
    NormativeAssertionProposal,
    NormativeForce,
)

STAT = "http://lunetix.org/standards-atlas#"
ONTOLOGY_VERSIONS = (
    "standards-atlas-core@2.0.0",
    "functional-safety@2.1.0",
)


def _proposal() -> DocumentKnowledgeProposal:
    evidence = "verification plan shall define verification criteria"
    anchor = EvidenceAnchor(
        id="anchor:C1:0",
        source_clause_id=ClauseId(value="C1"),
        source_kind=EvidenceSourceKind.BODY,
        start_offset=0,
        end_offset=len(evidence),
        content_hash=hashlib.sha256(evidence.encode()).hexdigest(),
    )
    plan = KnowledgeEntityProposal(
        id="entity:verification-plan",
        proposal_clause_ids=(ClauseId(value="C1"),),
        class_iri=f"{STAT}VerificationPlan",
        normalized_label="verification plan",
        source_anchor_ids=(anchor.id,),
        confidence=0.94,
        rationale="The source names the work product explicitly.",
    )
    criteria = KnowledgeEntityProposal(
        id="entity:verification-criteria",
        proposal_clause_ids=(ClauseId(value="C1"),),
        class_iri=f"{STAT}VerificationCriterion",
        normalized_label="verification criteria",
        source_anchor_ids=(anchor.id,),
        confidence=0.91,
    )
    assertion = NormativeAssertionProposal(
        id="assertion:C1:1",
        source_clause_id=ClauseId(value="C1"),
        subject_id=plan.id,
        predicate=f"{STAT}specifies",
        object=EntityAssertionObject(entity_id=criteria.id),
        normative_force=NormativeForce.REQUIREMENT,
        evidence_anchor_ids=(anchor.id,),
        confidence=0.89,
        rationale="The shall statement connects plan and criteria.",
    )
    return DocumentKnowledgeProposal(
        proposal_run_id="run-001",
        source_document_key="IEC61508-3",
        ontology_versions=ONTOLOGY_VERSIONS,
        evidence_anchors=(anchor,),
        entity_proposals=(plan, criteria),
        assertion_proposals=(assertion,),
        violations=(
            KnowledgeProposalViolation(
                clause_id=ClauseId(value="C1"),
                kind="ambiguous_grounding",
                term="assertion:C1:2",
                reason="The quoted evidence occurs more than once.",
            ),
        ),
        attempts=(
            KnowledgeProposalAttempt(
                clause_id=ClauseId(value="C1"),
                status="ok",
                duration_seconds=0.4,
                input_hash="1" * 64,
                raw_response_hash="2" * 64,
            ),
        ),
        proposal_provenance=KnowledgeProposalProvenance(
            extractor="formal-semantic-knowledge-extraction",
            extractor_version="2.0.0",
            model="example/model",
            provider="local",
            semantic_task="formal-semantic-knowledge-extraction@2.0.0",
            prompt_version="2.0.0",
        ),
    )


def test_confidence_and_rationale_exist_only_on_proposal_contracts() -> None:
    assert "confidence" in KnowledgeEntityProposal.model_fields
    assert "rationale" in KnowledgeEntityProposal.model_fields
    assert "confidence" in NormativeAssertionProposal.model_fields
    assert "rationale" in NormativeAssertionProposal.model_fields
    assert "confidence" not in KnowledgeEntity.model_fields
    assert "rationale" not in KnowledgeEntity.model_fields
    assert "confidence" not in NormativeAssertion.model_fields
    assert "rationale" not in NormativeAssertion.model_fields


def test_document_knowledge_proposal_roundtrips_with_noncanonical_metadata() -> None:
    proposal = _proposal()

    payload = proposal.model_dump(mode="json")
    restored = DocumentKnowledgeProposal.model_validate(payload)

    assert payload["schema_version"] == 1
    assert restored == proposal
    assert restored.entity_proposals[0].confidence == pytest.approx(0.94)
    assert restored.assertion_proposals[0].rationale is not None
    assert restored.violations[0].kind.value == "ambiguous_grounding"
    assert restored.proposal_provenance.model == "example/model"


@pytest.mark.parametrize("marker", [9, True, 1.0, "1"])
def test_document_knowledge_proposal_rejects_noncurrent_schema(marker: object) -> None:
    payload = _proposal().model_dump(mode="python")
    payload["schema_version"] = marker

    with pytest.raises(ValueError, match="unsupported document knowledge proposal schema version"):
        DocumentKnowledgeProposal.model_validate(payload)


def test_document_knowledge_proposal_requires_resolved_local_references() -> None:
    proposal = _proposal()
    assertion = proposal.assertion_proposals[0].model_copy(
        update={"object": EntityAssertionObject(entity_id="entity:missing")}
    )

    with pytest.raises(ValueError, match="unknown objects"):
        DocumentKnowledgeProposal(
            proposal_run_id=proposal.proposal_run_id,
            source_document_key=proposal.source_document_key,
            ontology_versions=proposal.ontology_versions,
            evidence_anchors=proposal.evidence_anchors,
            entity_proposals=proposal.entity_proposals,
            assertion_proposals=(assertion,),
            proposal_provenance=proposal.proposal_provenance,
        )

    entity = proposal.entity_proposals[0].model_copy(
        update={"source_anchor_ids": ("anchor:missing",)}
    )
    with pytest.raises(ValueError, match="unknown evidence anchors"):
        DocumentKnowledgeProposal(
            proposal_run_id=proposal.proposal_run_id,
            source_document_key=proposal.source_document_key,
            ontology_versions=proposal.ontology_versions,
            evidence_anchors=proposal.evidence_anchors,
            entity_proposals=(entity,),
            proposal_provenance=proposal.proposal_provenance,
        )


def test_proposal_semantics_require_explicit_ontology_versions_and_absolute_iris() -> None:
    proposal = _proposal()

    with pytest.raises(ValueError, match="require ontology_versions"):
        DocumentKnowledgeProposal(
            proposal_run_id=proposal.proposal_run_id,
            source_document_key=proposal.source_document_key,
            evidence_anchors=proposal.evidence_anchors,
            entity_proposals=proposal.entity_proposals,
            proposal_provenance=proposal.proposal_provenance,
        )

    with pytest.raises(ValueError, match="absolute IRI"):
        KnowledgeEntityProposal(
            id="entity:bad",
            proposal_clause_ids=(ClauseId(value="C1"),),
            class_iri="VerificationPlan",
            normalized_label="verification plan",
            source_anchor_ids=("anchor:C1:0",),
            confidence=0.9,
        )


def test_failed_attempts_require_error_metadata_and_terminal_failures_are_unique() -> None:
    with pytest.raises(ValueError, match="require error_type and message"):
        KnowledgeProposalAttempt(
            clause_id=ClauseId(value="C2"),
            status="timeout",
            duration_seconds=10.0,
        )

    proposal = _proposal()
    failure = KnowledgeProposalFailure(
        clause_id=ClauseId(value="C2"),
        kind="timeout",
        error_type="TimeoutError",
        message="request timed out",
    )
    with pytest.raises(ValueError, match="terminal clause failure only once"):
        DocumentKnowledgeProposal(
            proposal_run_id=proposal.proposal_run_id,
            source_document_key=proposal.source_document_key,
            proposal_provenance=proposal.proposal_provenance,
            failures=(failure, failure),
        )


def test_document_knowledge_proposal_input_lineage_is_unique_and_not_self_referential() -> None:
    proposal = _proposal()
    source = KnowledgeProposalInput(
        proposal_run_id="source-run",
        proposal_hash="a" * 64,
        proposal_provenance=proposal.proposal_provenance,
    )
    restored = proposal.model_copy(update={"input_proposals": (source,)})
    assert DocumentKnowledgeProposal.model_validate(restored.model_dump(mode="json")) == restored

    with pytest.raises(ValueError, match="input run ids must be unique"):
        DocumentKnowledgeProposal.model_validate(
            restored.model_copy(update={"input_proposals": (source, source)}).model_dump(
                mode="python"
            )
        )

    self_source = source.model_copy(update={"proposal_run_id": proposal.proposal_run_id})
    with pytest.raises(ValueError, match="cannot directly reference its own run"):
        DocumentKnowledgeProposal.model_validate(
            proposal.model_copy(update={"input_proposals": (self_source,)}).model_dump(
                mode="python"
            )
        )
