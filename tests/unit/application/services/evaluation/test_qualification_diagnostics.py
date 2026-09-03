from __future__ import annotations

from datetime import UTC, datetime

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


def _vote(model_id: str, present: bool) -> ModelVote:
    return ModelVote(
        model_id=model_id,
        applicability_present=present,
        repetitions=1,
        stability=1.0,
    )


def test_diagnostics_cluster_presence_conflicts_and_duplicates() -> None:
    text = "This part applies to railway software."
    clauses = (
        _clause(
            "one",
            "1",
            text,
            _vote("model-a", True),
            _vote("model-b", True),
            _vote("model-c", False),
        ),
        _clause(
            "two",
            "2",
            text,
            _vote("model-a", True),
            _vote("model-b", True),
            _vote("model-c", False),
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
    assert "polarity_disagreement_count" not in conflicts
    assert conflicts["clusters"][0] == {
        "signature": "present (2) ↔ absent (1)",
        "count": 2,
    }
    assert diagnostics["duplicate_clusters"]["exact_cluster_count"] == 1
    assert "multi_applicability_assertion_candidates" not in diagnostics

    markdown = render_qualification_diagnostics_markdown(
        report=report,
        diagnostics=diagnostics,
    )
    assert "Applicability conflict clusters" in markdown
    assert "Applicability model fitness signals" in markdown
    assert "Multiple applicability assertion candidates" not in markdown
    assert "observational only" in markdown


def test_applicability_model_fitness_respects_presence_eligibility() -> None:
    clause = _clause(
        "eligibility",
        "3",
        "This part applies to railway software.",
        ModelVote(
            model_id="presence-voter",
            applicability_present=True,
            applicability_presence_eligible=True,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="ineligible",
            applicability_present=False,
            applicability_presence_eligible=False,
            repetitions=1,
            stability=1.0,
        ),
    ).model_copy(
        update={
            "applicability_present": True,
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
    assert fitness["presence-voter"]["present_count"] == 1
    assert fitness["ineligible"]["vote_count"] == 0
