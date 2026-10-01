from __future__ import annotations

import hashlib

import pytest

from standards_atlas.application.assertion_qualification import (
    AssertionCandidateVerification,
    AssertionQualificationCascadeService,
    AssertionVerificationDisposition,
    AssertionVerifierProvenance,
)
from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionCascadeReason,
    AssertionCascadeRoute,
    AssertionClauseVerification,
)
from standards_atlas.application.context import ContextSelectionProfile
from standards_atlas.application.context.input_binding import context_source_package_binding
from standards_atlas.application.knowledge_proposal_extraction import (
    ProposalExtractionContext,
    assertion_context_source_package,
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
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[str] = []
        self.package_hashes: dict[str, str] = {}
        self.interpretation_contexts: dict[str, dict[str, object]] = {}

    def provenance(self) -> KnowledgeProposalProvenance:
        return KnowledgeProposalProvenance(
            extractor=self.name,
            extractor_version="1.0.0",
            model=f"{self.name}-model",
            request_contract_id="source-bound-knowledge-proposal-request-v1",
            output_contract_id="source-bound-knowledge-proposal-output-v1",
            source_binding_contract_id="source-bound-context-binding-v1",
        )

    def extract(
        self,
        clause,
        *,
        document_key,
        ontology_versions,
        source_package,
        interpretation_context=None,
    ):
        self.calls.append(clause.id.value)
        binding = context_source_package_binding(source_package)
        self.package_hashes[clause.id.value] = binding.package_sha256
        self.interpretation_contexts[clause.id.value] = dict(interpretation_context or {})
        text = clause.plain_text
        anchor = EvidenceAnchor(
            id=f"{self.name}:anchor:{clause.id.value}",
            source_clause_id=clause.id,
            source_kind=EvidenceSourceKind.BODY,
            start_offset=0,
            end_offset=len(text),
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
        )
        entity = KnowledgeEntityProposal(
            id=f"{self.name}:entity:{clause.id.value}",
            proposal_clause_ids=(clause.id,),
            class_iri=f"{STAT}Requirement",
            normalized_label=f"requirement {clause.id.value}",
            source_anchor_ids=(anchor.id,),
            confidence=0.9,
        )
        assertion = NormativeAssertionProposal(
            id=f"{self.name}:assertion:{clause.id.value}",
            source_clause_id=clause.id,
            subject_id=entity.id,
            predicate=f"{STAT}requires",
            object=EntityAssertionObject(entity_id=entity.id),
            normative_force=NormativeForce.REQUIREMENT,
            evidence_anchor_ids=(anchor.id,),
            confidence=0.9,
        )
        return ClauseKnowledgeProposalResult(
            clause_id=clause.id,
            evidence_anchors=(anchor,),
            entity_proposals=(entity,),
            assertion_proposals=(assertion,),
            source_package_binding=binding,
            proposal_provenance=self.provenance(),
            input_hash="1" * 64,
            raw_response_hash="2" * 64,
        )


class _Verifier:
    def __init__(self, missing_clause: str | None = None, *, wrong_binding: bool = False) -> None:
        self.missing_clause = missing_clause
        self.wrong_binding = wrong_binding
        self.calls: list[str] = []
        self.package_hashes: dict[str, str] = {}

    def provenance(self) -> AssertionVerifierProvenance:
        return AssertionVerifierProvenance(
            verifier="fake-verifier",
            verifier_version="1.0.0",
            model="verify-model",
            request_contract_id="source-bound-assertion-verifier-request-v1",
            source_binding_contract_id="source-bound-context-binding-v1",
        )

    def verify(
        self,
        clause,
        *,
        document_key,
        ontology_versions,
        evidence_anchors,
        entity_proposals,
        assertion_proposals,
        source_package,
        interpretation_context=None,
    ):
        self.calls.append(clause.id.value)
        binding = context_source_package_binding(source_package)
        self.package_hashes[clause.id.value] = binding.package_sha256
        missing = clause.id.value == self.missing_clause
        package_hash = "sha256:" + "f" * 64 if self.wrong_binding else binding.package_sha256
        return AssertionClauseVerification(
            clause_id=clause.id,
            entity_reviews=tuple(
                AssertionCandidateVerification(
                    candidate_id=item.id,
                    disposition=AssertionVerificationDisposition.SUPPORTED,
                )
                for item in entity_proposals
            ),
            assertion_reviews=tuple(
                AssertionCandidateVerification(
                    candidate_id=item.id,
                    disposition=AssertionVerificationDisposition.SUPPORTED,
                )
                for item in assertion_proposals
            ),
            missing_assertion_detected=missing,
            missing_rationale="one assertion is missing" if missing else None,
            input_hash="3" * 64,
            raw_response_hash="4" * 64,
            source_package_sha256=package_hash,
        )


def _clause(clause_id: str) -> Clause:
    return Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(standard="TEST", clause=clause_id),
        clause_type=ClauseType.REQUIREMENT,
        content=(TextBlock(id=f"t:{clause_id}", text=f"Clause {clause_id} requirement."),),
    )


def _document() -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(_clause("c1"), _clause("c2")),
    )


def test_cascade_shares_bound_source_package_with_extractor_and_verifier() -> None:
    efficient = _Extractor("efficient")
    escalation = _Extractor("escalation")
    verifier = _Verifier(missing_clause="c2")
    result = AssertionQualificationCascadeService(
        efficient_extractor=efficient,
        verifier=verifier,
        escalation_extractor=escalation,
    ).run_document(
        _document(),
        cascade_run_id="cascade-1",
        efficient_proposal_run_id="efficient-1",
        escalation_proposal_run_id="escalation-1",
        ontology_versions=ONTOLOGIES,
    )

    assert efficient.calls == ["c1", "c2"]
    assert verifier.calls == ["c1", "c2"]
    assert escalation.calls == ["c2"]
    assert efficient.package_hashes == verifier.package_hashes
    assert escalation.package_hashes["c2"] == efficient.package_hashes["c2"]
    assert len(result.source_packages) == 2
    assert [item.route for item in result.report.clauses] == [
        AssertionCascadeRoute.EFFICIENT_ACCEPTED,
        AssertionCascadeRoute.ESCALATED,
    ]
    assert result.report.clauses[1].reasons == (AssertionCascadeReason.MISSING_ASSERTION,)


def test_cascade_detects_verifier_source_package_mismatch() -> None:
    result = AssertionQualificationCascadeService(
        efficient_extractor=_Extractor("efficient"),
        verifier=_Verifier(wrong_binding=True),
        escalation_extractor=_Extractor("escalation"),
    ).run_document(
        _document(),
        cascade_run_id="cascade-mismatch",
        efficient_proposal_run_id="efficient-mismatch",
        escalation_proposal_run_id="escalation-mismatch",
        ontology_versions=ONTOLOGIES,
        clause_ids=frozenset({"c1"}),
    )

    clause = result.report.clauses[0]
    assert clause.route is AssertionCascadeRoute.ESCALATED
    assert clause.reasons == (AssertionCascadeReason.VERIFICATION_ERROR,)
    assert "different source package" in (clause.verification_error_message or "")


def test_verifier_must_review_every_efficient_candidate() -> None:
    class _IncompleteVerifier(_Verifier):
        def verify(self, clause, **kwargs):
            binding = context_source_package_binding(kwargs["source_package"])
            return AssertionClauseVerification(
                clause_id=clause.id,
                source_package_sha256=binding.package_sha256,
            )

    result = AssertionQualificationCascadeService(
        efficient_extractor=_Extractor("efficient"),
        verifier=_IncompleteVerifier(),
        escalation_extractor=_Extractor("escalation"),
    ).run_document(
        _document(),
        cascade_run_id="cascade-2",
        efficient_proposal_run_id="efficient-2",
        escalation_proposal_run_id="escalation-2",
        ontology_versions=ONTOLOGIES,
        clause_ids=frozenset({"c1"}),
    )

    clause = result.report.clauses[0]
    assert clause.route is AssertionCascadeRoute.ESCALATED
    assert clause.reasons == (AssertionCascadeReason.VERIFICATION_ERROR,)


def test_cascade_interpretation_metadata_is_source_free_and_shared() -> None:
    efficient = _Extractor("efficient")
    verifier = _Verifier(missing_clause="c1")
    escalation = _Extractor("escalation")
    AssertionQualificationCascadeService(
        efficient_extractor=efficient,
        verifier=verifier,
        escalation_extractor=escalation,
    ).run_document(
        _document(),
        cascade_run_id="cascade-context",
        efficient_proposal_run_id="efficient-context",
        escalation_proposal_run_id="escalation-context",
        ontology_versions=ONTOLOGIES,
        clause_ids=frozenset({"c1"}),
    )

    context = efficient.interpretation_contexts["c1"]
    assert "heading" not in context
    assert "ancestor_headings" not in context
    assert "associative_context" not in context
    assert escalation.interpretation_contexts["c1"] == context


def test_cascade_report_roundtrips_through_current_schema_writer(tmp_path) -> None:
    from standards_atlas.application.assertion_qualification import (
        load_assertion_qualification_cascade_report,
        write_assertion_qualification_cascade_report,
    )

    result = AssertionQualificationCascadeService(
        efficient_extractor=_Extractor("efficient"),
        verifier=_Verifier(),
        escalation_extractor=_Extractor("escalation"),
    ).run_document(
        _document(),
        cascade_run_id="cascade-roundtrip",
        efficient_proposal_run_id="efficient-roundtrip",
        escalation_proposal_run_id="escalation-roundtrip",
        ontology_versions=ONTOLOGIES,
        clause_ids=frozenset({"c1"}),
    )
    path = write_assertion_qualification_cascade_report(
        result.report,
        tmp_path / "assertion-cascade.json",
    )

    assert load_assertion_qualification_cascade_report(path) == result.report


def test_cascade_rejects_stale_supplied_package_after_document_change() -> None:
    original = _document()
    old_package = assertion_context_source_package(original, original.clauses[0])
    changed = original.model_copy(update={"clauses": (*original.clauses, _clause("c3"))})

    with pytest.raises(ValueError, match="stale for the current document revision"):
        AssertionQualificationCascadeService(
            efficient_extractor=_Extractor("efficient"),
            verifier=_Verifier(),
            escalation_extractor=_Extractor("escalation"),
        ).run_document(
            changed,
            cascade_run_id="cascade-stale",
            efficient_proposal_run_id="efficient-stale",
            escalation_proposal_run_id="escalation-stale",
            ontology_versions=ONTOLOGIES,
            clause_ids=frozenset({"c1"}),
            context_by_clause={
                "c1": ProposalExtractionContext(source_package=old_package),
            },
        )


def test_cascade_records_explicitly_changed_escalation_source_basis() -> None:
    document = _document()
    clause = document.clauses[0]
    efficient_package = assertion_context_source_package(document, clause)
    escalation_package = assertion_context_source_package(
        document,
        clause,
        profile=ContextSelectionProfile(character_budget=13_000),
    )
    efficient_binding = context_source_package_binding(efficient_package)
    escalation_binding = context_source_package_binding(escalation_package)
    assert escalation_binding.package_sha256 != efficient_binding.package_sha256

    result = AssertionQualificationCascadeService(
        efficient_extractor=_Extractor("efficient"),
        verifier=_Verifier(missing_clause="c1"),
        escalation_extractor=_Extractor("escalation"),
    ).run_document(
        document,
        cascade_run_id="cascade-rebound",
        efficient_proposal_run_id="efficient-rebound",
        escalation_proposal_run_id="escalation-rebound",
        ontology_versions=ONTOLOGIES,
        clause_ids=frozenset({"c1"}),
        context_by_clause={
            "c1": ProposalExtractionContext(source_package=efficient_package),
        },
        escalation_context_by_clause={
            "c1": ProposalExtractionContext(source_package=escalation_package),
        },
    )

    clause_report = result.report.clauses[0]
    assert clause_report.efficient_source_package_sha256 == efficient_binding.package_sha256
    assert clause_report.verifier_source_package_sha256 == efficient_binding.package_sha256
    assert clause_report.escalation_source_package_sha256 == escalation_binding.package_sha256
    assert clause_report.source_basis_changed is True
    assert len(result.source_packages) == 2
