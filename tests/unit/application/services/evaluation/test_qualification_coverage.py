from __future__ import annotations

from datetime import UTC, datetime

import pytest

from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
    OverallConsensusStatus,
)
from standards_atlas.application.semantic_qualification.qualification_coverage import (
    build_qualification_coverage,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
    QualificationSelectionClause,
)


def _selection() -> QualificationRunSelection:
    clauses = tuple(
        QualificationSelectionClause(
            example_id=f"example-{index}",
            document_key="DOC",
            clause_id=f"clause-{index}",
        )
        for index in range(1, 4)
    )
    return QualificationRunSelection(
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="semantic-profile-v1",
        dataset_sha256="a" * 64,
        corpus_sha256="b" * 64,
        dataset_clause_count=500,
        corpus_clause_count=500,
        selected_clause_count=3,
        clauses=clauses,
    )


def _report(*clause_ids: str) -> ConsensusReport:
    clauses = tuple(
        ClauseConsensus(
            clause_id=clause_id,
            document_key="DOC",
            category=ConsensusCategory.UNANIMOUS,
            overall_status=OverallConsensusStatus.RESOLVED,
            confidence=1.0,
            participating_models=3,
            requires_review=False,
        )
        for clause_id in clause_ids
    )
    return ConsensusReport(
        matrix_id="matrix-v1",
        corpus_id="semantic-profile-v1",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        generated_at=datetime.now(UTC),
        model_count=3,
        clause_count=len(clauses),
        categories={"unanimous": len(clauses)},
        review_count=0,
        clauses=clauses,
    )


def test_coverage_accounts_for_selected_clauses_without_consensus_result() -> None:
    coverage = build_qualification_coverage(
        selection=_selection(),
        report=_report("clause-1", "clause-3"),
    )

    assert coverage.selected_clause_count == 3
    assert coverage.qualified_clause_count == 2
    assert coverage.unqualified_clause_count == 1
    assert coverage.accounted_clause_count == 3
    assert [item.status for item in coverage.clauses] == [
        "qualified",
        "unqualified",
        "qualified",
    ]
    assert coverage.clauses[1].reason == "no_consensus_result"


def test_coverage_rejects_consensus_clause_outside_persisted_selection() -> None:
    with pytest.raises(ValueError, match="outside the persisted run selection"):
        build_qualification_coverage(
            selection=_selection(),
            report=_report("clause-1", "clause-unknown"),
        )
