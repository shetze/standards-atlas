from standards_atlas.adapters.governance import (
    GovernanceCandidateAnalyzer,
    render_candidate_analysis_csv,
    render_candidate_analysis_json,
)
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseSubjectContext,
    ClauseType,
    DocumentKey,
    GovernanceCandidateDecision,
    GovernanceSelectionProfile,
    KnowledgeKind,
    NormativeStatus,
    PrimarySubjectContext,
    ProcessFunction,
    SemanticClassification,
    StandardReference,
    StatementFunction,
    SubjectContextEvidence,
    SubjectEvidenceKind,
)
from standards_atlas.domain.model.content import TextBlock


def _clause(
    clause_id: str,
    clause_ref: str,
    text: str,
    *,
    statement: tuple[StatementFunction, ...] = (StatementFunction.REQUIREMENT,),
    process: tuple[ProcessFunction, ...] = (),
    knowledge: tuple[KnowledgeKind, ...] = (),
    applicability_present: bool = False,
    primary_subject: str | None = None,
    ambiguous_subjects: tuple[str, ...] = (),
) -> Clause:
    clause = Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(standard="EN50716", year=2023, clause=clause_ref),
        clause_type=ClauseType.REQUIREMENT,
        content=(TextBlock(id=f"{clause_id}-text", text=text),),
        normative_status=NormativeStatus.NORMATIVE,
        semantic_classification=SemanticClassification(
            statement_functions=statement,
            process_functions=process,
            knowledge_kinds=knowledge,
            applicability_present=applicability_present,
        ),
    )
    if primary_subject is not None or ambiguous_subjects:
        evidence = (
            SubjectContextEvidence(
                kind=SubjectEvidenceKind.CLAUSE_TEXT,
                matched_label=primary_subject,
                source_text=text,
                source_clause_id=clause_id,
            )
            if primary_subject is not None
            else None
        )
        clause = clause.with_subject_context(
            ClauseSubjectContext(
                primary_subject=(
                    PrimarySubjectContext(
                        normalized_label=primary_subject,
                        confidence=1.0,
                        evidence=evidence,
                    )
                    if primary_subject is not None and evidence is not None
                    else None
                ),
                ambiguous_candidates=ambiguous_subjects,
            )
        )
    return clause


def _document(*clauses: Clause) -> PublicationDocument:
    return PublicationDocument(
        key=DocumentKey(value="EN50716"),
        title="EN 50716",
        year=2023,
        clauses=clauses,
    )


def _profile(**selection: object) -> GovernanceSelectionProfile:
    return GovernanceSelectionProfile.model_validate(
        {
            "id": "rail-onboard",
            "version": "1.0.0",
            "context": {"domain": "railway"},
            "standards": {"include": ["EN50716"]},
            "selection": selection,
        }
    )


def test_candidate_is_selected_when_qualified_semantics_match() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "The software shall be verified.",
            process=(ProcessFunction.ACTIVITY,),
            knowledge=(KnowledgeKind.PROCESS,),
        )
    )
    profile = _profile(
        **{
            "process-functions": ["activity"],
            "knowledge-kinds": ["process"],
            "statement-functions": ["requirement"],
        }
    )

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    assert analysis.selected == 1
    assert analysis.candidates[0].decision is GovernanceCandidateDecision.SELECTED


def test_candidate_is_excluded_on_explicit_semantic_mismatch() -> None:
    document = _document(
        _clause("c1", "5.1", "The software shall be verified.", process=(ProcessFunction.ACTIVITY,))
    )
    profile = _profile(**{"process-functions": ["output"]})

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    assert analysis.excluded == 1
    assert analysis.candidates[0].decision is GovernanceCandidateDecision.EXCLUDED


def test_missing_requested_semantics_are_undetermined() -> None:
    document = _document(_clause("c1", "5.1", "The software shall be verified."))
    profile = _profile(**{"knowledge-kinds": ["evidence"]})

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    assert analysis.undetermined == 1
    assert analysis.candidates[0].decision is GovernanceCandidateDecision.UNDETERMINED


def test_renderers_are_deterministic_and_review_friendly() -> None:
    document = _document(_clause("c1", "5.1", "The software shall be verified."))
    analysis = GovernanceCandidateAnalyzer().analyze(_profile(), (document,))

    assert render_candidate_analysis_json(analysis) == render_candidate_analysis_json(analysis)
    csv_text = render_candidate_analysis_csv(analysis)
    assert "control_id" in csv_text
    assert "selected" in csv_text


def test_clause_local_selection_does_not_cross_match_dimensions() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "Requirement about software design.",
            statement=(StatementFunction.REQUIREMENT,),
            primary_subject="software design",
        ),
        _clause(
            "c2",
            "5.2",
            "Conformance statement about safety lifecycle.",
            statement=(StatementFunction.CONFORMANCE_STATEMENT,),
            primary_subject="safety lifecycle",
        ),
    )
    profile = _profile(
        **{
            "statement-functions": ["requirement"],
            "primary-subjects": ["safety lifecycle"],
        }
    )

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    assert analysis.selected == 0
    assert all(
        candidate.decision is not GovernanceCandidateDecision.SELECTED
        for candidate in analysis.candidates
    )


def test_clause_local_selection_selects_when_one_clause_matches_all_dimensions() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "Requirement about safety lifecycle.",
            statement=(StatementFunction.REQUIREMENT,),
            primary_subject="safety lifecycle",
        )
    )
    profile = _profile(
        **{
            "statement-functions": ["requirement"],
            "primary-subjects": ["safety lifecycle"],
        }
    )

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    candidate = analysis.candidates[0]
    assert candidate.decision is GovernanceCandidateDecision.SELECTED
    assert candidate.matching_clause_ids == ("c1",)
    assert candidate.matching_primary_subjects == ("safety lifecycle",)


def test_subject_group_is_expanded_and_recorded_in_analysis() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "Requirement about safety lifecycle.",
            primary_subject="safety lifecycle",
        )
    )
    profile = _profile(
        **{
            "statement-functions": ["requirement"],
            "subject-group-profile": {"id": "functional-safety", "version": "1.0.0"},
            "primary-subject-groups": ["safety-lifecycle"],
        }
    )

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    assert analysis.subject_selection.subject_group_profile is not None
    assert analysis.subject_selection.subject_group_profile.id == "functional-safety"
    assert "safety lifecycle" in analysis.subject_selection.effective_primary_subjects
    assert analysis.candidates[0].decision is GovernanceCandidateDecision.SELECTED


def test_missing_primary_subject_is_undetermined_when_subject_filter_is_active() -> None:
    document = _document(_clause("c1", "5.1", "Requirement with no subject."))
    profile = _profile(**{"primary-subjects": ["safety lifecycle"]})

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    candidate = analysis.candidates[0]
    assert candidate.decision is GovernanceCandidateDecision.UNDETERMINED
    assert candidate.undetermined_clause_ids == ("c1",)


def test_review_csv_exposes_clause_and_subject_provenance() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "Requirement about safety lifecycle.",
            primary_subject="safety lifecycle",
        )
    )
    analysis = GovernanceCandidateAnalyzer().analyze(
        _profile(**{"primary-subjects": ["safety lifecycle"]}),
        (document,),
    )

    csv_text = render_candidate_analysis_csv(analysis)

    assert "matching_clause_ids" in csv_text
    assert "matching_primary_subjects" in csv_text
    assert "safety lifecycle" in csv_text
