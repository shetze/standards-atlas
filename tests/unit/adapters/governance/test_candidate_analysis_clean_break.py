from standards_atlas.adapters.governance import GovernanceCandidateAnalyzer
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseSubjectContext,
    ClauseType,
    DocumentKey,
    GovernanceCandidateDecision,
    GovernanceContext,
    GovernanceSelectionProfile,
    GovernanceSemanticSelection,
    PrimarySubjectContext,
    StandardReference,
    SubjectContextEvidence,
    SubjectEvidenceKind,
    TextBlock,
)


def test_governance_selection_uses_primary_subject_without_legacy_semantics() -> None:
    objective = Clause(
        id=ClauseId(value="obj"),
        reference=StandardReference(standard="EN50716", year=2023, clause="6"),
        clause_type=ClauseType.OBJECTIVE,
        content=(TextBlock(id="obj-text", text="Verify the software."),),
    )
    requirement = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="EN50716", year=2023, clause="6.1"),
        clause_type=ClauseType.REQUIREMENT,
        baseline={
            "parent_id": objective.id,
            "content": (
                TextBlock(id="req-text", text="Software verification shall be performed."),
            ),
        },
        enrichments={
            "subject_context": ClauseSubjectContext(
                primary_subject=PrimarySubjectContext(
                    normalized_label="software verification",
                    confidence=1.0,
                    evidence=SubjectContextEvidence(
                        kind=SubjectEvidenceKind.CLAUSE_TEXT,
                        matched_label="software verification",
                        source_text="software verification",
                        source_clause_id="c1",
                    ),
                )
            )
        },
    )
    document = PublicationDocument(
        key=DocumentKey(value="EN50716"),
        title="EN 50716",
        year=2023,
        clauses=(objective, requirement),
    )
    profile = GovernanceSelectionProfile(
        id="verification",
        version="1",
        context=GovernanceContext(domain="railway"),
        selection=GovernanceSemanticSelection.model_validate(
            {"primary-subjects": ["software verification"]}
        ),
    )
    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))
    assert analysis.selected == 1
    assert analysis.candidates[0].decision is GovernanceCandidateDecision.SELECTED
    assert "c1" in analysis.candidates[0].matching_clause_ids
