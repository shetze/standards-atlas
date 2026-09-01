from standards_atlas.adapters.governance import (
    GovernanceCandidateAnalyzer,
    render_candidate_analysis_csv,
    render_candidate_analysis_json,
)
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    GovernanceCandidateDecision,
    GovernanceSelectionProfile,
    KnowledgeKind,
    NormativeStatus,
    ProcessFunction,
    SemanticClassification,
    StandardReference,
    StatementFunction,
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
) -> Clause:
    return Clause(
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


def test_required_applicability_without_evidence_is_undetermined() -> None:
    document = _document(_clause("c1", "5.1", "The software shall be verified."))
    profile = GovernanceSelectionProfile.model_validate(
        {
            "id": "rail-onboard",
            "version": "1.0.0",
            "context": {"domain": "railway"},
            "standards": {"include": ["EN50716"]},
            "applicability": {"require-present": True},
        }
    )

    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    assert analysis.undetermined == 1


def test_renderers_are_deterministic_and_review_friendly() -> None:
    document = _document(_clause("c1", "5.1", "The software shall be verified."))
    analysis = GovernanceCandidateAnalyzer().analyze(_profile(), (document,))

    assert render_candidate_analysis_json(analysis) == render_candidate_analysis_json(analysis)
    csv_text = render_candidate_analysis_csv(analysis)
    assert "control_id" in csv_text
    assert "selected" in csv_text
