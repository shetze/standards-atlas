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
    clause_type: ClauseType = ClauseType.REQUIREMENT,
    parent_id: str | None = None,
    statement: tuple[StatementFunction, ...] = (StatementFunction.REQUIREMENT,),
    process: tuple[ProcessFunction, ...] = (),
    knowledge: tuple[KnowledgeKind, ...] = (),
    subject: str | None = None,
    ambiguous_subjects: tuple[str, ...] = (),
) -> Clause:
    clause = Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(
            standard="EN50716",
            year=2023,
            clause=clause_ref,
        ),
        clause_type=clause_type,
        parent_id=ClauseId(value=parent_id) if parent_id is not None else None,
        content=(TextBlock(id=f"{clause_id}-text", text=text),),
        normative_status=NormativeStatus.NORMATIVE,
        semantic_classification=SemanticClassification(
            statement_functions=statement,
            process_functions=process,
            knowledge_kinds=knowledge,
        ),
    )
    if subject is None and not ambiguous_subjects:
        return clause
    primary = None
    if subject is not None:
        primary = PrimarySubjectContext(
            normalized_label=subject,
            confidence=1.0,
            evidence=SubjectContextEvidence(
                kind=SubjectEvidenceKind.CLAUSE_TEXT,
                matched_label=subject,
                source_text=text,
                source_clause_id=clause_id,
            ),
        )
    return clause.with_subject_context(
        ClauseSubjectContext(
            primary_subject=primary,
            ambiguous_candidates=ambiguous_subjects,
        )
    )


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
            "schema-version": 2,
            "id": "rail-onboard",
            "version": "1.0.0",
            "context": {"domain": "railway"},
            "standards": {"include": ["EN50716"]},
            "selection": selection,
        }
    )


def _anchored_control(*requirements: Clause) -> PublicationDocument:
    objective = _clause(
        "obj",
        "5",
        "Verification objective.",
        clause_type=ClauseType.OBJECTIVE,
        statement=(StatementFunction.OBJECTIVE,),
        subject="software design",
    )
    attached = tuple(
        item.model_copy(
            update={
                "baseline": item.baseline.model_copy(update={"parent_id": ClauseId(value="obj")})
            }
        )
        for item in requirements
    )
    return _document(objective, *attached)


def test_candidate_is_selected_when_qualified_semantics_match_on_same_clause() -> None:
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

    assert analysis.schema_version == 2
    assert analysis.selected == 1
    candidate = analysis.candidates[0]
    assert candidate.decision is GovernanceCandidateDecision.SELECTED
    assert candidate.matching_clause_ids == ("c1",)
    assert candidate.clause_results[0].decision is GovernanceCandidateDecision.SELECTED


def test_candidate_is_excluded_on_explicit_semantic_mismatch() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "The software shall be verified.",
            process=(ProcessFunction.ACTIVITY,),
        )
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
    assert analysis.candidates[0].undetermined_clause_ids == ("c1",)


def test_direct_primary_subject_selection_is_supported() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "The safety lifecycle shall be defined.",
            subject="safety lifecycle",
        )
    )
    profile = _profile(
        **{
            "statement-functions": ["requirement"],
            "primary-subjects": ["Safety Lifecycle"],
        }
    )

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    assert analysis.selected == 1
    assert analysis.subject_selection.effective_subjects == ("safety lifecycle",)
    assert analysis.candidates[0].matching_clause_ids == ("c1",)


def test_subject_group_is_expanded_before_candidate_analysis() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "The software lifecycle shall be defined.",
            subject="software lifecycle",
        )
    )
    profile = _profile(
        **{
            "statement-functions": ["requirement"],
            "subject-group-profile": {
                "id": "functional-safety",
                "version": "1.0.0",
            },
            "primary-subject-groups": ["safety-lifecycle"],
        }
    )

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    assert analysis.selected == 1
    assert analysis.subject_selection.profile_id == "functional-safety"
    assert analysis.subject_selection.profile_version == "1.0.0"
    assert analysis.subject_selection.requested_groups == ("safety-lifecycle",)
    assert analysis.subject_selection.effective_subjects == (
        "safety lifecycle",
        "software lifecycle",
    )


def test_dimensions_do_not_cross_match_between_different_clauses() -> None:
    document = _anchored_control(
        _clause(
            "r1",
            "5.1",
            "The software design shall be verified.",
            statement=(StatementFunction.REQUIREMENT,),
            subject="software design",
        ),
        _clause(
            "r2",
            "5.2",
            "Conformance to the lifecycle shall be demonstrated.",
            statement=(StatementFunction.CONFORMANCE_STATEMENT,),
            subject="safety lifecycle",
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
    candidate = analysis.candidates[0]
    assert candidate.decision is GovernanceCandidateDecision.EXCLUDED
    assert candidate.matching_clause_ids == ()
    assert {item.clause_id: item.decision for item in candidate.clause_results} == {
        "obj": GovernanceCandidateDecision.EXCLUDED,
        "r1": GovernanceCandidateDecision.EXCLUDED,
        "r2": GovernanceCandidateDecision.EXCLUDED,
    }


def test_one_clause_matching_all_dimensions_selects_the_control() -> None:
    document = _anchored_control(
        _clause(
            "r1",
            "5.1",
            "The safety lifecycle shall be verified.",
            statement=(StatementFunction.REQUIREMENT,),
            subject="safety lifecycle",
        ),
        _clause(
            "r2",
            "5.2",
            "Conformance to the software design shall be demonstrated.",
            statement=(StatementFunction.CONFORMANCE_STATEMENT,),
            subject="software design",
        ),
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
    assert candidate.matching_clause_ids == ("r1",)


def test_missing_primary_subject_keeps_candidate_undetermined_when_no_clause_matches() -> None:
    document = _anchored_control(
        _clause(
            "r1",
            "5.1",
            "The lifecycle shall be verified.",
            statement=(StatementFunction.REQUIREMENT,),
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
    assert candidate.decision is GovernanceCandidateDecision.UNDETERMINED
    assert "r1" in candidate.undetermined_clause_ids


def test_ambiguous_primary_subject_is_reported_as_undetermined_evidence() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "The lifecycle shall be verified.",
            ambiguous_subjects=("safety lifecycle", "software lifecycle"),
        )
    )
    profile = _profile(**{"primary-subjects": ["safety lifecycle"]})

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    result = analysis.candidates[0].clause_results[0]
    assert result.decision is GovernanceCandidateDecision.UNDETERMINED
    assert result.ambiguous_subjects == ("safety lifecycle", "software lifecycle")
    assert result.signals[0].reason == "clause primary subject is ambiguous"


def test_empty_statement_functions_do_not_restrict_primary_subject_selection() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "Lifecycle information.",
            subject="safety lifecycle",
            statement=(StatementFunction.DESCRIPTION,),
        )
    )
    profile = _profile(
        **{
            "statement-functions": [],
            "primary-subjects": ["safety lifecycle"],
        }
    )

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    assert analysis.candidates[0].decision is GovernanceCandidateDecision.SELECTED


def test_values_within_one_dimension_use_or_semantics() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "The safety lifecycle shall be defined.",
            subject="safety lifecycle",
            statement=(StatementFunction.REQUIREMENT,),
        )
    )
    profile = _profile(
        **{
            "statement-functions": ["prohibition", "requirement"],
            "primary-subjects": ["software design", "safety lifecycle"],
        }
    )

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    assert analysis.candidates[0].decision is GovernanceCandidateDecision.SELECTED


def test_renderers_include_clause_level_review_evidence() -> None:
    document = _document(
        _clause(
            "c1",
            "5.1",
            "The safety lifecycle shall be verified.",
            subject="safety lifecycle",
        )
    )
    analysis = GovernanceCandidateAnalyzer().analyze(
        _profile(**{"primary-subjects": ["safety lifecycle"]}),
        (document,),
    )

    json_text = render_candidate_analysis_json(analysis)
    assert json_text == render_candidate_analysis_json(analysis)
    assert '"schema-version": 2' in json_text
    assert '"effective-subjects"' in json_text
    assert '"clause-results"' in json_text

    csv_text = render_candidate_analysis_csv(analysis)
    assert "matching_clause_ids" in csv_text
    assert "matching_primary_subjects" in csv_text
    assert "safety lifecycle" in csv_text
