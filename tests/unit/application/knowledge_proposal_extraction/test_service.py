from standards_atlas.application.knowledge_proposal_extraction import (
    KnowledgeProposalExtractionService,
    proposal_extraction_eligibility,
)
from standards_atlas.application.ports import ClauseKnowledgeProposalResult
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    EntityAssertionObject,
    EvidenceAnchor,
    EvidenceSourceKind,
    KnowledgeEntityProposal,
    KnowledgeProposalProvenance,
    NormativeAssertionProposal,
    NormativeForce,
    StandardReference,
    TextBlock,
)

STAT = "http://lunetix.org/standards-atlas#"
ONTOLOGIES = ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")


class _Extractor:
    def __init__(self) -> None:
        self.calls = []

    def provenance(self) -> KnowledgeProposalProvenance:
        return KnowledgeProposalProvenance(
            extractor="fake",
            extractor_version="1",
            model="fake-model",
            semantic_task="formal-semantic-knowledge-proposal",
            prompt_version="test-v1",
        )

    def extract(self, clause, *, document_key, ontology_versions, semantic_context=None):
        self.calls.append((clause.id.value, semantic_context))
        anchor = EvidenceAnchor(
            id=f"a:{clause.id.value}",
            source_clause_id=clause.id,
            source_kind=EvidenceSourceKind.BODY,
            start_offset=0,
            end_offset=len(clause.plain_text),
        )
        entity = KnowledgeEntityProposal(
            id=f"e:{clause.id.value}",
            proposal_clause_ids=(clause.id,),
            class_iri=f"{STAT}Requirement",
            normalized_label="requirement",
            source_anchor_ids=(anchor.id,),
            confidence=0.9,
        )
        assertion = NormativeAssertionProposal(
            id=f"n:{clause.id.value}",
            source_clause_id=clause.id,
            subject_id=entity.id,
            predicate=f"{STAT}requires",
            object=EntityAssertionObject(entity_id=entity.id),
            normative_force=NormativeForce.REQUIREMENT,
            evidence_anchor_ids=(anchor.id,),
            confidence=0.8,
        )
        return ClauseKnowledgeProposalResult(
            clause_id=clause.id,
            evidence_anchors=(anchor,),
            entity_proposals=(entity,),
            assertion_proposals=(assertion,),
            proposal_provenance=self.provenance(),
            input_hash="1" * 64,
            raw_response_hash="2" * 64,
        )


def _clause(clause_id: str, clause_type: ClauseType, text: str) -> Clause:
    content = (TextBlock(id=f"t:{clause_id}", text=text),) if text else ()
    return Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(standard="TEST", clause=clause_id),
        clause_type=clause_type,
        content=content,
    )


def test_eligibility_is_broad_and_not_dependent_on_applicability() -> None:
    assert proposal_extraction_eligibility(
        _clause("body", ClauseType.CLAUSE, "Descriptive engineering content.")
    ).eligible
    assert not proposal_extraction_eligibility(_clause("toc", ClauseType.TOC, "Contents")).eligible
    assert not proposal_extraction_eligibility(
        _clause("table", ClauseType.TABLE, "Structured table text")
    ).eligible
    assert not proposal_extraction_eligibility(_clause("empty", ClauseType.CLAUSE, "")).eligible


def test_service_aggregates_clause_results_into_run_scoped_proposal() -> None:
    extractor = _Extractor()
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test standard",
        document_type=DocumentType.STANDARD,
        clauses=(
            _clause("c1", ClauseType.CLAUSE, "An engineering statement."),
            _clause("toc", ClauseType.TOC, "Contents"),
        ),
    )

    proposal = KnowledgeProposalExtractionService(extractor).extract_document(
        document,
        proposal_run_id="run-5b",
        ontology_versions=ONTOLOGIES,
    )

    assert proposal.proposal_run_id == "run-5b"
    assert proposal.source_document_key == "TEST"
    assert proposal.ontology_versions == ONTOLOGIES
    assert len(proposal.evidence_anchors) == 1
    assert len(proposal.entity_proposals) == 1
    assert len(proposal.assertion_proposals) == 1
    assert proposal.failures == ()
    assert len(proposal.attempts) == 1
    assert proposal.attempts[0].input_hash == "1" * 64
    assert [call[0] for call in extractor.calls] == ["c1"]
