from __future__ import annotations

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
from standards_atlas.application.ports import ClauseKnowledgeProposalResult
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    ContextRouting,
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
    ReferenceRole,
    ReferenceRouting,
    ReferenceTarget,
    StandardReference,
    StructuralContext,
    StructuralNodeKind,
    StructuralSiblingContext,
    TextBlock,
)

STAT = "http://lunetix.org/standards-atlas#"
ONTOLOGIES = ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")


class _Extractor:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[str] = []
        self.contexts: dict[str, dict[str, object]] = {}

    def provenance(self) -> KnowledgeProposalProvenance:
        return KnowledgeProposalProvenance(
            extractor=self.name,
            extractor_version="1.0.0",
            model=f"{self.name}-model",
        )

    def extract(self, clause, *, document_key, ontology_versions, semantic_context=None):
        self.calls.append(clause.id.value)
        self.contexts[clause.id.value] = dict(semantic_context or {})
        anchor = EvidenceAnchor(
            id=f"{self.name}:anchor:{clause.id.value}",
            source_clause_id=clause.id,
            source_kind=EvidenceSourceKind.BODY,
            start_offset=0,
            end_offset=len(clause.plain_text),
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
            proposal_provenance=self.provenance(),
            input_hash="1" * 64,
            raw_response_hash="2" * 64,
        )


class _Verifier:
    def __init__(self, missing_clause: str | None = None) -> None:
        self.missing_clause = missing_clause
        self.calls: list[str] = []
        self.contexts: dict[str, dict[str, object]] = {}

    def provenance(self) -> AssertionVerifierProvenance:
        return AssertionVerifierProvenance(
            verifier="fake-verifier",
            verifier_version="1.0.0",
            model="verify-model",
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
        semantic_context=None,
    ):
        self.calls.append(clause.id.value)
        self.contexts[clause.id.value] = dict(semantic_context or {})
        missing = clause.id.value == self.missing_clause
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


def test_cascade_accepts_supported_clause_and_escalates_missing_assertion() -> None:
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
    assert result.escalation_proposal is not None
    assert [item.route for item in result.report.clauses] == [
        AssertionCascadeRoute.EFFICIENT_ACCEPTED,
        AssertionCascadeRoute.ESCALATED,
    ]
    assert result.report.clauses[1].reasons == (AssertionCascadeReason.MISSING_ASSERTION,)
    assert result.report.efficient_accepted_clauses == 1
    assert result.report.escalated_clauses == 1
    assert [item.stage for item in result.report.proposal_sources] == [
        "efficient",
        "escalation",
    ]


def test_verifier_must_review_every_efficient_candidate() -> None:
    class _IncompleteVerifier(_Verifier):
        def verify(self, clause, **kwargs):
            return AssertionClauseVerification(clause_id=clause.id)

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
    assert clause.verification_error_type == "ValueError"


def test_cascade_transports_same_structural_and_reference_cbox_to_all_stages() -> None:
    parent = Clause(
        id=ClauseId(value="parent"),
        reference=StandardReference(standard="TEST", clause="7.4.4.3"),
        clause_type=ClauseType.CLAUSE,
        heading="Route 2H",
    )
    child = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="TEST", clause="7.4.4.3.1"),
        clause_type=ClauseType.REQUIREMENT,
        baseline={
            "parent_id": parent.id,
            "content": (TextBlock(id="t:c1", text="Requirement unless 7.4.4.3.2 applies."),),
            "structural_context": StructuralContext(
                node_kind=StructuralNodeKind.LEAF,
                sibling=StructuralSiblingContext(
                    index=0,
                    count=3,
                    is_first=True,
                    is_last=False,
                    next_clause_id="c2",
                ),
            ),
        },
        enrichments={
            "context_routing": ContextRouting(
                references=(
                    ReferenceRouting(
                        source_clause_id="c1",
                        target=ReferenceTarget(
                            document_key="TEST",
                            clause_id="c2",
                            reference="7.4.4.3.2",
                        ),
                        role=ReferenceRole.PROVIDES_EXCEPTION,
                        evidence=("unless 7.4.4.3.2 applies",),
                    ),
                )
            )
        },
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(parent, child),
    )
    efficient = _Extractor("efficient")
    verifier = _Verifier(missing_clause="c1")
    escalation = _Extractor("escalation")

    AssertionQualificationCascadeService(
        efficient_extractor=efficient,
        verifier=verifier,
        escalation_extractor=escalation,
    ).run_document(
        document,
        cascade_run_id="cascade-context",
        efficient_proposal_run_id="efficient-context",
        escalation_proposal_run_id="escalation-context",
        ontology_versions=ONTOLOGIES,
        clause_ids=frozenset({"c1"}),
    )

    contexts = (
        efficient.contexts["c1"],
        verifier.contexts["c1"],
        escalation.contexts["c1"],
    )
    assert contexts[0] == contexts[1] == contexts[2]
    context = contexts[0]
    assert context["parent_id"] == "parent"
    assert context["ancestor_headings"] == [
        {"clause_id": "parent", "reference": "7.4.4.3", "heading": "Route 2H"}
    ]
    assert context["structural_context"]["sibling"]["is_first"] is True
    assert context["structural_context"]["sibling"]["next_clause_id"] == "c2"
    assert context["context_routing"]["references"][0]["role"] == "provides_exception"
    assert context["context_routing"]["references"][0]["target"]["reference"] == "7.4.4.3.2"


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


def test_verifier_checks_for_missing_assertions_when_efficient_output_is_empty() -> None:
    class _EmptyExtractor(_Extractor):
        def extract(self, clause, *, document_key, ontology_versions, semantic_context=None):
            self.calls.append(clause.id.value)
            return ClauseKnowledgeProposalResult(
                clause_id=clause.id,
                proposal_provenance=self.provenance(),
                input_hash="5" * 64,
                raw_response_hash="6" * 64,
            )

    efficient = _EmptyExtractor("efficient")
    verifier = _Verifier(missing_clause="c1")
    escalation = _Extractor("escalation")
    result = AssertionQualificationCascadeService(
        efficient_extractor=efficient,
        verifier=verifier,
        escalation_extractor=escalation,
    ).run_document(
        _document(),
        cascade_run_id="cascade-empty",
        efficient_proposal_run_id="efficient-empty",
        escalation_proposal_run_id="escalation-empty",
        ontology_versions=ONTOLOGIES,
        clause_ids=frozenset({"c1"}),
    )

    assert verifier.calls == ["c1"]
    assert result.report.clauses[0].efficient_entities == 0
    assert result.report.clauses[0].efficient_assertions == 0
    assert result.report.clauses[0].reasons == (AssertionCascadeReason.MISSING_ASSERTION,)
    assert escalation.calls == ["c1"]


def test_cascade_keeps_entity_grounded_in_ancestor_heading_with_source_clause() -> None:
    parent = Clause(
        id=ClauseId(value="parent"),
        reference=StandardReference(standard="TEST", clause="12.3.1"),
        clause_type=ClauseType.CLAUSE,
        heading="Random hardware fault quantitative analysis",
    )
    child = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="TEST", clause="12.3.1.3"),
        clause_type=ClauseType.CLAUSE,
        baseline={
            "parent_id": parent.id,
            "heading": (
                "Emergency Operation Time Interval calculation if no PMHF value is available"
            ),
            "content": (TextBlock(id="t:c1", text="If the method is used, the criteria apply."),),
        },
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(parent, child),
    )

    class _HeadingExtractor(_Extractor):
        def extract(self, clause, *, document_key, ontology_versions, semantic_context=None):
            self.calls.append(clause.id.value)
            self.contexts[clause.id.value] = dict(semantic_context or {})
            heading = parent.heading or ""
            anchor = EvidenceAnchor(
                id="heading-anchor",
                source_clause_id=parent.id,
                source_kind=EvidenceSourceKind.HEADING,
                start_offset=0,
                end_offset=len(heading),
            )
            entity = KnowledgeEntityProposal(
                id="heading-entity",
                proposal_clause_ids=(clause.id,),
                class_iri=f"{STAT}Activity",
                normalized_label="random hardware fault quantitative analysis",
                source_anchor_ids=(anchor.id,),
                confidence=0.9,
            )
            return ClauseKnowledgeProposalResult(
                clause_id=clause.id,
                evidence_anchors=(anchor,),
                entity_proposals=(entity,),
                proposal_provenance=self.provenance(),
                input_hash="1" * 64,
                raw_response_hash="2" * 64,
            )

    class _CaptureVerifier(_Verifier):
        def __init__(self) -> None:
            super().__init__()
            self.entity_ids: tuple[str, ...] = ()
            self.anchor_source_ids: tuple[str, ...] = ()

        def verify(self, clause, **kwargs):
            self.calls.append(clause.id.value)
            entities = tuple(kwargs["entity_proposals"])
            anchors = tuple(kwargs["evidence_anchors"])
            self.entity_ids = tuple(item.id for item in entities)
            self.anchor_source_ids = tuple(item.source_clause_id.value for item in anchors)
            return AssertionClauseVerification(
                clause_id=clause.id,
                entity_reviews=tuple(
                    AssertionCandidateVerification(
                        candidate_id=item.id,
                        disposition=AssertionVerificationDisposition.SUPPORTED,
                    )
                    for item in entities
                ),
                assertion_reviews=(),
                input_hash="3" * 64,
                raw_response_hash="4" * 64,
            )

    efficient = _HeadingExtractor("efficient")
    verifier = _CaptureVerifier()
    result = AssertionQualificationCascadeService(
        efficient_extractor=efficient,
        verifier=verifier,
        escalation_extractor=_Extractor("escalation"),
    ).run_document(
        document,
        cascade_run_id="cascade-heading",
        efficient_proposal_run_id="efficient-heading",
        escalation_proposal_run_id="escalation-heading",
        ontology_versions=ONTOLOGIES,
        clause_ids=frozenset({"c1"}),
    )

    assert verifier.entity_ids == ("heading-entity",)
    assert verifier.anchor_source_ids == ("parent",)
    assert result.report.clauses[0].route is AssertionCascadeRoute.EFFICIENT_ACCEPTED
