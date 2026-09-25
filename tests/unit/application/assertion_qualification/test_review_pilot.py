from __future__ import annotations

import hashlib

import pytest

from standards_atlas.application.assertion_qualification import (
    ApplicabilitySelectionCase,
    ApplicabilitySelectionCorpus,
    AssertionCandidateVerification,
    AssertionCascadeClauseReport,
    AssertionCascadeProposalSource,
    AssertionClauseVerification,
    AssertionGoldenPartition,
    AssertionQualificationCascadeReport,
    AssertionReviewAssertion,
    AssertionReviewEntity,
    AssertionReviewEvidenceSpan,
    AssertionReviewExpected,
    AssertionReviewPilotBuildRequest,
    AssertionReviewStatus,
    AssertionReviewTargetSuite,
    AssertionVerificationDisposition,
    AssertionVerifierProvenance,
    attach_cascade_to_assertion_review_pilot,
    build_assertion_review_pilot,
    proposal_sha256,
    publish_assertion_review_pilot,
    review_clause_ids,
    select_applicability_pilot_cases,
    validate_assertion_review_pilot_document,
)
from standards_atlas.application.assertion_qualification.review_pilot_models import (
    ApplicabilitySelectionExpected,
    ApplicabilitySelectionProvenance,
)
from standards_atlas.application.knowledge_proposal_extraction import assertion_cbox_context
from standards_atlas.domain.model import (
    CanonicalDocumentSection,
    Clause,
    ClauseId,
    ClauseType,
    ContextRouting,
    DocumentKey,
    DocumentKnowledgeProposal,
    DocumentType,
    EngineeringDocument,
    EntityAssertionObject,
    EvidenceAnchor,
    EvidenceSourceKind,
    GeneratedAttribute,
    GenerationMethod,
    KnowledgeEntityProposal,
    KnowledgeProposalProvenance,
    NormativeForce,
    NormativeStatus,
    ScopeDeclaration,
    ScopeReach,
    ScopeReachKind,
    SemanticSection,
    SemanticSectionRole,
    StandardReference,
    StructuralProfile,
    TextBlock,
)

STAT = "http://lunetix.org/standards-atlas#"
ONTOLOGIES = ("standards-atlas-core@2.0.0",)


def _source_case(
    *,
    clause_id: str,
    document_key: str = "DOC",
    reference: str = "DOC:1",
    text: str = "The verification plan shall specify the verification criteria.",
    present: bool = False,
    category: str = "minority_presence_disagreement",
) -> ApplicabilitySelectionCase:
    return ApplicabilitySelectionCase(
        clause_id=clause_id,
        document_key=document_key,
        reference=reference,
        text=text,
        category=category,
        status="published",
        expected=ApplicabilitySelectionExpected(present=present),
        provenance=ApplicabilitySelectionProvenance(
            source_archive="qualification-run.zip",
            source_archive_sha256="a" * 64,
        ),
    )


def _document(*cases: ApplicabilitySelectionCase) -> EngineeringDocument:
    clauses = tuple(
        Clause(
            id=ClauseId(value=case.clause_id),
            reference=StandardReference(
                standard=case.document_key,
                clause=case.reference.rsplit(":", 1)[1],
            ),
            clause_type=ClauseType.REQUIREMENT,
            content=(TextBlock(id=f"text-{index}", text=case.text),),
        )
        for index, case in enumerate(cases)
    )
    return EngineeringDocument(
        key=DocumentKey(value=cases[0].document_key),
        title="Test document",
        document_type=DocumentType.OTHER,
        clauses=clauses,
    )


def _corpus(*cases: ApplicabilitySelectionCase) -> ApplicabilitySelectionCorpus:
    return ApplicabilitySelectionCorpus(
        corpus_id="applicability-hard-cases",
        corpus_version="3.0.0",
        cases=cases,
    )


def _request(*, clause_ids: tuple[str, ...] = ()) -> AssertionReviewPilotBuildRequest:
    return AssertionReviewPilotBuildRequest(
        review_id="pilot",
        review_version="0.1.0",
        target_suite=AssertionReviewTargetSuite(
            id="pilot-dev",
            version="0.1.0",
            partition=AssertionGoldenPartition.DEVELOPMENT,
            ontology_versions=ONTOLOGIES,
        ),
        source_corpus_sha256="b" * 64,
        clause_ids=clause_ids,
    )


def test_stratified_selection_is_deterministic_and_keeps_both_applicability_values() -> None:
    cases = tuple(
        _source_case(
            clause_id=f"c{index}",
            document_key=f"DOC{index % 3}",
            reference=f"DOC{index % 3}:{index}",
            text=f"text {index}",
            present=index % 2 == 0,
            category=(
                "balanced_presence_disagreement"
                if index % 3 == 0
                else "minority_presence_disagreement"
            ),
        )
        for index in range(12)
    )
    corpus = _corpus(*cases)

    first = select_applicability_pilot_cases(corpus, limit=6)
    second = select_applicability_pilot_cases(corpus, limit=6)

    assert first == second
    assert {case.expected.present for case in first if case.expected is not None} == {False, True}
    assert len({case.document_key for case in first}) >= 2


def test_stratified_selection_filters_back_matter_and_annex_zz_before_sampling() -> None:
    regular_a = _source_case(clause_id="a", document_key="A", reference="A:1", text="regular A")
    annex_zz = _source_case(
        clause_id="zz", document_key="B", reference="B:ZZ", text="regulatory back matter"
    )
    regular_c = _source_case(clause_id="c", document_key="C", reference="C:2", text="regular C")
    corpus = _corpus(regular_a, annex_zz, regular_c)
    documents = {
        "A": _document(regular_a),
        "B": _document(annex_zz),
        "C": _document(regular_c),
    }

    selected = select_applicability_pilot_cases(corpus, limit=2, documents=documents)

    assert [case.clause_id for case in selected] == ["a", "c"]
    assert "zz" not in {case.clause_id for case in selected}


def test_scope_filter_keeps_substantive_child_under_heading_only_parent() -> None:
    source = _source_case(
        clause_id="child",
        document_key="DOC",
        reference="DOC:7.4.4.3.1",
        text="A substantive child requirement.",
    )
    parent = Clause(
        id=ClauseId(value="parent"),
        reference=StandardReference(standard="DOC", clause="7.4.4.3"),
        clause_type=ClauseType.CLAUSE,
        heading="Route 2H",
    )
    child = Clause(
        id=ClauseId(value="child"),
        reference=StandardReference(standard="DOC", clause="7.4.4.3.1"),
        clause_type=ClauseType.REQUIREMENT,
        parent_id=parent.id,
        content=(TextBlock(id="text-child", text=source.text),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Test document",
        document_type=DocumentType.OTHER,
        clauses=(parent, child),
    )

    selected = select_applicability_pilot_cases(
        _corpus(source), limit=1, documents={"DOC": document}
    )

    assert selected == (source,)


def test_build_binds_source_case_to_current_clause_and_records_text_drift() -> None:
    source = _source_case(clause_id="c1")
    document = _document(source)
    pilot = build_assertion_review_pilot(
        _corpus(source),
        (source,),
        {"DOC": document},
        _request(clause_ids=("c1",)),
    )

    assert pilot.cases[0].text == source.text
    assert pilot.cases[0].text_sha256 == hashlib.sha256(source.text.encode()).hexdigest()
    assert pilot.cases[0].applicability_source.present is False
    assert (
        pilot.cases[0].applicability_source.selection_text_sha256
        == hashlib.sha256(source.text.encode()).hexdigest()
    )
    assert pilot.cases[0].applicability_source.selection_text_matches_current is True
    assert pilot.cases[0].expected is None
    assert pilot.cases[0].review_status is AssertionReviewStatus.PENDING
    assert pilot.cases[0].context == assertion_cbox_context(document, document.clauses[0])

    drifted = source.model_copy(update={"text": source.text + " changed"})
    drifted_pilot = build_assertion_review_pilot(
        _corpus(drifted),
        (drifted,),
        {"DOC": document},
        _request(clause_ids=("c1",)),
    )

    assert drifted_pilot.cases[0].text == source.text
    assert drifted_pilot.cases[0].text_sha256 == hashlib.sha256(source.text.encode()).hexdigest()
    assert (
        drifted_pilot.cases[0].applicability_source.selection_text_sha256
        == hashlib.sha256(drifted.text.encode()).hexdigest()
    )
    assert drifted_pilot.cases[0].applicability_source.selection_text_matches_current is False


def test_publish_merges_case_local_entities_and_computes_exact_evidence_hashes() -> None:
    first = _source_case(clause_id="c1", reference="DOC:1")
    second = _source_case(
        clause_id="c2",
        reference="DOC:2",
        text="The verification plan shall be reviewed.",
    )
    pilot = build_assertion_review_pilot(
        _corpus(first, second),
        (first, second),
        {"DOC": _document(first, second)},
        _request(clause_ids=("c1", "c2")),
    )

    plan_entity_1 = AssertionReviewEntity(
        id="plan",
        class_iri=f"{STAT}VerificationPlan",
        normalized_label="Verification Plan",
    )
    criteria_entity = AssertionReviewEntity(
        id="criteria",
        class_iri=f"{STAT}Criterion",
        normalized_label="Verification Criteria",
    )
    start = first.text.index("verification plan")
    first_expected = AssertionReviewExpected(
        entities=(plan_entity_1, criteria_entity),
        assertions=(
            AssertionReviewAssertion(
                id="a1",
                subject_id="plan",
                predicate=f"{STAT}specifies",
                object=EntityAssertionObject(entity_id="criteria"),
                normative_force=NormativeForce.REQUIREMENT,
                evidence=(
                    AssertionReviewEvidenceSpan(start_offset=start, end_offset=len(first.text)),
                ),
            ),
        ),
    )
    second_expected = AssertionReviewExpected(
        entities=(
            AssertionReviewEntity(
                id="same-plan-different-local-id",
                class_iri=f"{STAT}VerificationPlan",
                normalized_label="  verification   plan  ",
            ),
        ),
        assertions=(),
    )
    completed = pilot.model_copy(
        update={
            "cases": (
                pilot.cases[0].model_copy(
                    update={
                        "review_status": AssertionReviewStatus.REVIEWED,
                        "expected": first_expected,
                    }
                ),
                pilot.cases[1].model_copy(
                    update={
                        "review_status": AssertionReviewStatus.REVIEWED,
                        "expected": second_expected,
                    }
                ),
            )
        }
    )

    suite = publish_assertion_review_pilot(completed)

    assert len(suite.cases) == 1
    case = suite.cases[0]
    assert len(case.entities) == 2
    assert len(case.assertions) == 1
    evidence = case.assertions[0].evidence[0]
    assert evidence.clause_id.value == "c1"
    assert evidence.content_hash == hashlib.sha256(first.text[start:].encode()).hexdigest()


def test_publish_requires_every_selected_case_to_be_reviewed() -> None:
    source = _source_case(clause_id="c1")
    pilot = build_assertion_review_pilot(
        _corpus(source),
        (source,),
        {"DOC": _document(source)},
        _request(clause_ids=("c1",)),
    )

    with pytest.raises(ValueError, match="pending cases"):
        publish_assertion_review_pilot(pilot)


def test_attach_uses_exact_cascade_selection_and_final_route_proposal() -> None:
    source = _source_case(clause_id="c1")
    pilot = build_assertion_review_pilot(
        _corpus(source),
        (source,),
        {"DOC": _document(source)},
        _request(clause_ids=("c1",)),
    )
    text = source.text
    anchor = EvidenceAnchor(
        id="anchor-1",
        source_clause_id=ClauseId(value="c1"),
        source_kind=EvidenceSourceKind.BODY,
        start_offset=0,
        end_offset=len(text),
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )
    efficient = DocumentKnowledgeProposal(
        proposal_run_id="efficient-run",
        source_document_key="DOC",
        ontology_versions=ONTOLOGIES,
        evidence_anchors=(anchor,),
        entity_proposals=(
            KnowledgeEntityProposal(
                id="plan",
                proposal_clause_ids=(ClauseId(value="c1"),),
                class_iri=f"{STAT}VerificationPlan",
                normalized_label="Verification Plan",
                source_anchor_ids=(anchor.id,),
                confidence=0.9,
            ),
        ),
        assertion_proposals=(),
        proposal_provenance=KnowledgeProposalProvenance(
            extractor="test",
            extractor_version="1.0.0",
        ),
    )
    verification = AssertionClauseVerification(
        clause_id=ClauseId(value="c1"),
        entity_reviews=(
            AssertionCandidateVerification(
                candidate_id="plan",
                disposition=AssertionVerificationDisposition.SUPPORTED,
            ),
        ),
    )
    cascade = AssertionQualificationCascadeReport(
        cascade_run_id="cascade-run",
        source_document_key="DOC",
        ontology_versions=ONTOLOGIES,
        proposal_sources=(
            AssertionCascadeProposalSource(
                stage="efficient",
                proposal_run_id=efficient.proposal_run_id,
                proposal_hash=proposal_sha256(efficient),
                extractor="test",
                extractor_version="1.0.0",
            ),
        ),
        verifier_provenance=AssertionVerifierProvenance(
            verifier="test-verifier",
            verifier_version="1.0.0",
        ),
        clauses=(
            AssertionCascadeClauseReport(
                clause_id=ClauseId(value="c1"),
                route="efficient_accepted",
                verification=verification,
                efficient_entities=1,
                efficient_assertions=0,
            ),
        ),
        efficient_accepted_clauses=1,
        escalated_clauses=0,
    )

    updated = attach_cascade_to_assertion_review_pilot(
        pilot,
        cascade=cascade,
        efficient=efficient,
        escalation=None,
    )

    assert review_clause_ids(updated, document_key="DOC") == ("c1",)
    snapshot = updated.cases[0].proposal
    assert snapshot is not None
    assert snapshot.proposal_stage == "efficient"
    assert snapshot.entities[0].normalized_label == "Verification Plan"
    assert snapshot.verifier_dispositions == {"plan": "supported"}


def test_review_document_validation_detects_source_changes_after_pilot_build() -> None:
    source = _source_case(clause_id="c1")
    document = _document(source)
    pilot = build_assertion_review_pilot(
        _corpus(source),
        (source,),
        {"DOC": document},
        _request(clause_ids=("c1",)),
    )
    assert validate_assertion_review_pilot_document(pilot, document) == ("c1",)

    changed_source = source.model_copy(update={"text": source.text + " changed"})
    changed_document = _document(changed_source)
    with pytest.raises(ValueError, match="source text changed"):
        validate_assertion_review_pilot_document(pilot, changed_document)


def _known_scope_clause(
    *,
    clause_id: str = "scope",
    qualification: str = "It has an informative character only.",
    reach: ScopeReach | None = None,
) -> Clause:
    routing = ContextRouting(
        scopes=(
            ScopeDeclaration(
                source_clause_id=clause_id,
                reaches=(reach or ScopeReach(kind=ScopeReachKind.DOCUMENT, document_key="DOC"),),
                qualifications=(qualification,),
                evidence=(qualification,),
            ),
        )
    )
    clause = Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(standard="DOC", clause="1"),
        clause_type=ClauseType.SCOPE,
        heading="Scope",
        content=(TextBlock(id="scope-text", text=qualification),),
    ).with_context_routing(routing)
    return clause.mark_generated(
        GeneratedAttribute(
            path="enrichments.context_routing",
            generator="test/context-routing",
            method=GenerationMethod.LLM,
        )
    )


def test_assertion_cbox_projects_governing_scope_and_informative_normative_context() -> None:
    scope = _known_scope_clause()
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="DOC", clause="5.1"),
        clause_type=ClauseType.REQUIREMENT,
        heading="Requirement",
        content=(TextBlock(id="target-text", text="The criterion is applicable."),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Technical standard",
        document_type=DocumentType.OTHER,
        clauses=(scope, target),
    )

    context = assertion_cbox_context(document, target)

    assert context["canonical_cbox_version"] == "1.3"
    assert len(context["governing_scopes"]) == 1
    governing = context["governing_scopes"][0]
    assert governing["source_clause_id"] == "scope"
    assert governing["qualifications"] == ["It has an informative character only."]
    assert context["normative_context"]["source_status"] == "informative"
    assert context["normative_context"]["effective_status"] == "informative"
    assert context["normative_context"]["basis"][0]["kind"] == ("governing_scope_qualification")


def test_assertion_cbox_synthesizes_structural_document_scope_when_routing_is_missing() -> None:
    qualification = (
        "This document provides additional explanations. "
        "It has an informative character only and describes the general concepts."
    )
    scope = Clause(
        id=ClauseId(value="scope"),
        reference=StandardReference(standard="DOC", clause="1"),
        clause_type=ClauseType.SCOPE,
        heading="Scope",
        content=(TextBlock(id="scope-text", text=qualification),),
        structural_profile=StructuralProfile(canonical_section=CanonicalDocumentSection.SCOPE),
    )
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="DOC", clause="5.1"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="target-text", text="The criterion is applicable."),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Technical overview",
        document_type=DocumentType.OTHER,
        clauses=(scope, target),
    )

    context = assertion_cbox_context(document, target)

    assert len(context["governing_scopes"]) == 1
    governing = context["governing_scopes"][0]
    assert governing["source_clause_id"] == "scope"
    assert governing["reaches"] == [
        {
            "kind": "document",
            "document_key": "DOC",
            "part": None,
            "clause_id": None,
            "reference": None,
        }
    ]
    assert governing["qualifications"] == [
        "It has an informative character only and describes the general concepts."
    ]
    assert context["normative_context"]["source_status"] == "informative"
    assert context["normative_context"]["basis"][0]["kind"] == ("governing_scope_qualification")


def test_assertion_cbox_rejects_non_scope_document_wide_routing() -> None:
    misleading = _known_scope_clause(
        clause_id="ordinary",
        qualification="It has an informative character only.",
    ).model_copy(update={"clause_type": ClauseType.REQUIREMENT})
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="DOC", clause="5.1"),
        clause_type=ClauseType.REQUIREMENT,
        content=(TextBlock(id="target-text", text="The supplier shall record the result."),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Technical standard",
        document_type=DocumentType.OTHER,
        clauses=(misleading, target),
    )

    context = assertion_cbox_context(document, target)

    assert context["governing_scopes"] == []
    assert context["normative_context"]["source_status"] == "normative"
    assert context["normative_context"]["basis"][-1]["kind"] == "default_standard_context"


def test_assertion_cbox_keeps_local_scope_from_non_scope_clause() -> None:
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="DOC", clause="7.4.4.3.1"),
        clause_type=ClauseType.REQUIREMENT,
        content=(TextBlock(id="target-text", text="The supplier shall record the result."),),
    )
    routing = ContextRouting(
        scopes=(
            ScopeDeclaration(
                source_clause_id="exception",
                reaches=(
                    ScopeReach(
                        kind=ScopeReachKind.CLAUSE,
                        document_key="DOC",
                        clause_id="target",
                    ),
                ),
                conditions=("unless the conditions apply",),
                evidence=("unless the conditions apply",),
            ),
        )
    )
    source = Clause(
        id=ClauseId(value="exception"),
        reference=StandardReference(standard="DOC", clause="7.4.4.3.2"),
        clause_type=ClauseType.REQUIREMENT,
        content=(TextBlock(id="exception-text", text="unless the conditions apply"),),
    ).with_context_routing(routing)
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Technical standard",
        document_type=DocumentType.OTHER,
        clauses=(source, target),
    )

    context = assertion_cbox_context(document, target)

    assert len(context["governing_scopes"]) == 1
    assert context["governing_scopes"][0]["source_clause_id"] == "exception"
    assert context["governing_scopes"][0]["conditions"] == ["unless the conditions apply"]


def test_assertion_cbox_ignores_scope_that_does_not_reach_target() -> None:
    root = Clause(
        id=ClauseId(value="root"),
        reference=StandardReference(standard="DOC", clause="4"),
        clause_type=ClauseType.CLAUSE,
        heading="Scoped subtree",
    )
    scope = _known_scope_clause(
        reach=ScopeReach(
            kind=ScopeReachKind.SUBTREE,
            document_key="DOC",
            clause_id="root",
        )
    )
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="DOC", clause="5.1"),
        clause_type=ClauseType.REQUIREMENT,
        content=(TextBlock(id="target-text", text="The supplier shall record the result."),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Technical standard",
        document_type=DocumentType.OTHER,
        clauses=(scope, root, target),
    )

    context = assertion_cbox_context(document, target)

    assert context["governing_scopes"] == []
    assert context["normative_context"]["effective_status"] == "normative"
    assert context["normative_context"]["basis"][-1]["kind"] == "default_standard_context"


def test_assertion_cbox_inherits_informative_ancestor_heading() -> None:
    root = Clause(
        id=ClauseId(value="root"),
        reference=StandardReference(standard="DOC", clause="C"),
        clause_type=ClauseType.CLAUSE,
        heading="Guidance for the confirmation measures",
    )
    section = Clause(
        id=ClauseId(value="section"),
        reference=StandardReference(standard="DOC", clause="C.4"),
        clause_type=ClauseType.CLAUSE,
        heading="Confirmation review of the safety plan",
        parent_id=ClauseId(value="root"),
    )
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="DOC", clause="C.4.4"),
        clause_type=ClauseType.OBJECTIVE,
        heading="OBJECTIVE",
        parent_id=ClauseId(value="section"),
        content=(TextBlock(id="target-text", text="Evaluation of the applied tailoring."),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Management of functional safety",
        document_type=DocumentType.OTHER,
        clauses=(root, section, target),
    )

    normative = assertion_cbox_context(document, target)["normative_context"]

    assert normative["source_status"] == "informative"
    assert normative["effective_status"] == "informative"
    assert normative["basis"] == [
        {
            "kind": "ancestor_heading",
            "status": "informative",
            "source_clause_id": "root",
            "source_reference": "C",
            "value": "Guidance for the confirmation measures",
        }
    ]


def test_assertion_cbox_recognizes_guideline_document_title_as_informative() -> None:
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="DOC", clause="12.3.1.3"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="target-text", text="The criteria is applicable."),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Guidelines on application of the standard",
        document_type=DocumentType.OTHER,
        clauses=(target,),
    )

    context = assertion_cbox_context(document, target)

    assert context["normative_context"]["source_status"] == "informative"
    assert context["normative_context"]["effective_status"] == "informative"
    assert context["normative_context"]["basis"][0]["kind"] == "document_title"


def test_assertion_cbox_defaults_unmarked_standard_clause_to_normative() -> None:
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="DOC", clause="7.1"),
        clause_type=ClauseType.REQUIREMENT,
        content=(TextBlock(id="target-text", text="The supplier shall record the result."),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Safety requirements",
        document_type=DocumentType.OTHER,
        clauses=(target,),
    )

    context = assertion_cbox_context(document, target)

    assert context["normative_context"] == {
        "source_status": "normative",
        "effective_status": "normative",
        "fallback_status": "normative",
        "basis": [
            {
                "kind": "default_standard_context",
                "status": "normative",
                "value": "standards content is normative unless informative evidence applies",
            }
        ],
        "span_overrides": [],
    }


def test_assertion_cbox_treats_terms_and_example_headings_as_informative() -> None:
    term = Clause(
        id=ClauseId(value="term"),
        reference=StandardReference(standard="DOC", clause="3.1"),
        clause_type=ClauseType.TERM,
        heading="verification",
        content=(TextBlock(id="term-text", text="confirmation by objective evidence"),),
    )
    example = Clause(
        id=ClauseId(value="example"),
        reference=StandardReference(standard="DOC", clause="A.2"),
        clause_type=ClauseType.CLAUSE,
        heading="Example of failure mode for PLD",
        content=(TextBlock(id="example-text", text="A failure can occur when ..."),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Safety requirements",
        document_type=DocumentType.OTHER,
        clauses=(term, example),
    )

    term_context = assertion_cbox_context(document, term)["normative_context"]
    example_context = assertion_cbox_context(document, example)["normative_context"]

    assert term_context["source_status"] == "normative"
    assert term_context["effective_status"] == "informative"
    assert term_context["basis"][-1]["kind"] == "clause_type"
    assert example_context["source_status"] == "normative"
    assert example_context["effective_status"] == "informative"
    assert example_context["basis"][-1]["kind"] == "local_heading"


def test_assertion_cbox_marks_note_example_and_description_spans_informative() -> None:
    text = "Requirement text.\nDescription: descriptive method.\nNOTE explanatory note."
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="DOC", clause="7.1"),
        clause_type=ClauseType.REQUIREMENT,
        structural_profile=StructuralProfile(
            canonical_section=CanonicalDocumentSection.BODY,
            semantic_sections=(
                SemanticSection(
                    label="Description",
                    role=SemanticSectionRole.DESCRIPTION,
                    start_offset=18,
                    end_offset=50,
                ),
                SemanticSection(
                    label="NOTE",
                    role=SemanticSectionRole.NOTE,
                    start_offset=50,
                    end_offset=len(text),
                ),
            ),
        ),
        content=(TextBlock(id="target-text", text=text),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Safety requirements",
        document_type=DocumentType.OTHER,
        clauses=(target,),
    )

    normative = assertion_cbox_context(document, target)["normative_context"]

    assert normative["effective_status"] == "normative"
    assert [(item["role"], item["status"]) for item in normative["span_overrides"]] == [
        ("description", "informative"),
        ("note", "informative"),
    ]


def test_explicit_informative_clause_status_overrides_normative_default() -> None:
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="DOC", clause="A.1"),
        clause_type=ClauseType.CLAUSE,
        normative_status=NormativeStatus.INFORMATIVE,
        content=(TextBlock(id="target-text", text="Informative annex content."),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Safety requirements",
        document_type=DocumentType.OTHER,
        clauses=(target,),
    )

    normative = assertion_cbox_context(document, target)["normative_context"]

    assert normative["source_status"] == "informative"
    assert normative["effective_status"] == "informative"
    assert normative["basis"][0]["kind"] == "clause_normative_status"
