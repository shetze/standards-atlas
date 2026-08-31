from __future__ import annotations

from datetime import UTC, datetime

from standards_atlas.application.semantic_qualification.applicability_contract import (
    ApplicabilityPolarity,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
    ModelVote,
    OverallConsensusStatus,
)
from standards_atlas.application.semantic_qualification.diagnostics import (
    build_qualification_diagnostics,
    render_qualification_diagnostics_markdown,
)


def _clause(
    clause_id: str,
    reference: str,
    text: str,
    *votes: ModelVote,
) -> ClauseConsensus:
    return ClauseConsensus(
        clause_id=clause_id,
        document_key="DOC",
        reference=reference,
        clause_text=text,
        category=ConsensusCategory.DISPUTED,
        applicability_category=ConsensusCategory.DISPUTED,
        overall_status=OverallConsensusStatus.REVIEW_REQUIRED,
        confidence=0.5,
        participating_models=len(votes),
        votes=votes,
        requires_review=True,
    )


def _vote(
    model_id: str,
    polarity: ApplicabilityPolarity | None,
) -> ModelVote:
    return ModelVote(
        model_id=model_id,
        applicability_present=polarity is not None,
        applicability_polarity=polarity,
        repetitions=1,
        stability=1.0,
    )


def test_diagnostics_cluster_conflicts_duplicates_and_multi_assertions() -> None:
    text = "This part does not apply to medical equipment. The requirement applies to ASIL C."
    clauses = (
        _clause(
            "one",
            "1",
            text,
            _vote("model-a", ApplicabilityPolarity.EXCLUDED),
            _vote("model-b", ApplicabilityPolarity.INCLUDED),
            _vote("model-c", None),
        ),
        _clause(
            "two",
            "2",
            text,
            _vote("model-a", ApplicabilityPolarity.EXCLUDED),
            _vote("model-b", ApplicabilityPolarity.INCLUDED),
            _vote("model-c", None),
        ),
    )
    report = ConsensusReport(
        matrix_id="matrix-v1",
        corpus_id="corpus-v1",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        generated_at=datetime.now(UTC),
        model_count=3,
        clause_count=2,
        categories={"disputed": 2},
        review_count=2,
        clauses=clauses,
    )

    diagnostics = build_qualification_diagnostics(report=report, cascade_stages=[])

    conflicts = diagnostics["applicability_conflicts"]
    assert conflicts["clause_count"] == 2
    assert conflicts["presence_disagreement_count"] == 2
    assert conflicts["polarity_disagreement_count"] == 2
    assert conflicts["clusters"][0]["count"] == 2
    assert diagnostics["duplicate_clusters"]["exact_cluster_count"] == 1
    candidates = diagnostics["multi_applicability_assertion_candidates"]
    assert len(candidates) == 2
    assert set(candidates[0]["detected_polarities"]) == {
        "included",
        "excluded",
    }

    markdown = render_qualification_diagnostics_markdown(
        report=report,
        diagnostics=diagnostics,
    )
    assert "Applicability conflict clusters" in markdown
    assert "Applicability model fitness signals" in markdown
    assert "Multiple applicability assertion candidates" in markdown
    assert "observational only" in markdown


def test_applicability_model_fitness_respects_dimension_eligibility() -> None:
    clause = _clause(
        "eligibility",
        "3",
        "This part applies to railway software.",
        ModelVote(
            model_id="presence-voter",
            applicability_present=True,
            applicability_polarity=ApplicabilityPolarity.INCLUDED,
            applicability_presence_eligible=True,
            applicability_polarity_eligible=True,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="polarity-only",
            applicability_present=False,
            applicability_presence_eligible=False,
            applicability_polarity_eligible=True,
            repetitions=1,
            stability=1.0,
        ),
    ).model_copy(
        update={
            "applicability_present": True,
            "applicability_polarity": ApplicabilityPolarity.INCLUDED,
            "applicability_category": ConsensusCategory.UNANIMOUS,
        }
    )
    report = ConsensusReport(
        matrix_id="matrix-v1",
        corpus_id="corpus-v1",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        generated_at=datetime.now(UTC),
        model_count=2,
        clause_count=1,
        categories={"unanimous": 1},
        review_count=0,
        clauses=(clause,),
    )

    diagnostics = build_qualification_diagnostics(report=report, cascade_stages=[])
    fitness = {item["model_id"]: item for item in diagnostics["applicability_model_fitness"]}

    assert fitness["presence-voter"]["vote_count"] == 1
    assert fitness["polarity-only"]["vote_count"] == 0
