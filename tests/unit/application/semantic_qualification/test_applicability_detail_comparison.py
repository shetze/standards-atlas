from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCase,
    ApplicabilityGoldenCorpus,
    ApplicabilityGoldenExpected,
    ApplicabilityGoldenProvenance,
)
from standards_atlas.application.semantic_qualification.applicability_detail_comparison import (
    ApplicabilityCandidateTargetPattern,
    compare_applicability_detail_contracts,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    APPLICABILITY_DETAIL_REPORT_FILENAME,
    APPLICABILITY_DETAIL_SELECTION_FILENAME,
    ApplicabilityDetailClauseResult,
    ApplicabilityDetailEnrichmentReport,
    ApplicabilityDetailEvidence,
    ApplicabilityDetailGenerator,
    ApplicabilityDetailOutcome,
    ApplicabilityDetailRunStatistics,
    ApplicabilityDetailSelection,
    ApplicabilityDetailSelectionClause,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
)
from standards_atlas.domain.model import (
    ApplicabilityFunction,
    ApplicabilityTarget,
    OtherApplicabilityTarget,
)

NOW = datetime(2026, 9, 6, tzinfo=UTC)
SHA_A = "a" * 64
SHA_C = "c" * 64


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _golden_case(index: int, *, present: bool) -> ApplicabilityGoldenCase:
    return ApplicabilityGoldenCase(
        clause_id=f"clause-{index}",
        document_key="ISO26262-X",
        reference=f"ISO26262-X:{index}",
        text=f"Clause {index}",
        category="comparison",
        status="published",
        expected=ApplicabilityGoldenExpected(present=present),
        provenance=ApplicabilityGoldenProvenance(
            source_archive="qualification-run-073.zip",
            source_archive_sha256=SHA_A,
        ),
    )


def _consensus_clause(index: int, *, present: bool) -> ClauseConsensus:
    return ClauseConsensus(
        clause_id=f"clause-{index}",
        document_key="ISO26262-X",
        reference=f"ISO26262-X:{index}",
        category=ConsensusCategory.UNANIMOUS,
        applicability_category=ConsensusCategory.UNANIMOUS,
        applicability_present=present,
        applicability_presence_confidence=1.0,
        confidence=1.0,
        participating_models=3,
        requires_review=False,
    )


def _selection_clause(index: int) -> ApplicabilityDetailSelectionClause:
    return ApplicabilityDetailSelectionClause(
        example_id=f"example-{index}",
        document_key="ISO26262-X",
        clause_id=f"clause-{index}",
        content_hash=f"sha256:{index:064x}",
        reference=f"ISO26262-X:{index}",
        presence_confidence=1.0,
        presence_category="unanimous",
        source_requires_review=False,
        presence_resolution_source="final-cascade",
    )


def _generator(index: int, *, v2: bool) -> ApplicabilityDetailGenerator:
    return ApplicabilityDetailGenerator(
        model_id="qwen",
        model="qwen/model",
        provider="ramalama",
        task_version="2.0.0" if v2 else "1.0.0",
        prompt_version="detail-structure-aware-v2" if v2 else "detail-structure-aware-v1",
        input_hash=f"input-{index}-{'v2' if v2 else 'v1'}",
        raw_response_hash=f"response-{index}-{'v2' if v2 else 'v1'}",
        duration_ms=10,
        cached=False,
        generated_at=NOW,
    )


def _v1_result(
    index: int,
    *,
    clause: bool,
) -> ApplicabilityDetailClauseResult:
    common = dict(
        example_id=f"example-{index}",
        document_key="ISO26262-X",
        clause_id=f"clause-{index}",
        content_hash=f"sha256:{index:064x}",
        reference=f"ISO26262-X:{index}",
        presence_confidence=1.0,
        generator=_generator(index, v2=False),
        evidence_grounded=True,
    )
    if not clause:
        return ApplicabilityDetailClauseResult(
            **common,
            outcome=ApplicabilityDetailOutcome.NOT_CONFIRMED,
            applicability_target=ApplicabilityTarget.METHOD_OR_TECHNIQUE,
        )
    return ApplicabilityDetailClauseResult(
        **common,
        outcome=ApplicabilityDetailOutcome.ENRICHED,
        applicability_target=ApplicabilityTarget.CLAUSE_OR_REQUIREMENT,
        applicability_functions=(ApplicabilityFunction.INCLUSION,),
        evidence=(
            ApplicabilityDetailEvidence(
                function=ApplicabilityFunction.INCLUSION,
                text="Clause applicability evidence",
            ),
        ),
    )


def _v2_result(
    index: int,
    *,
    clause: bool,
    other_targets: tuple[OtherApplicabilityTarget, ...] = (),
) -> ApplicabilityDetailClauseResult:
    common = dict(
        example_id=f"example-{index}",
        document_key="ISO26262-X",
        clause_id=f"clause-{index}",
        content_hash=f"sha256:{index:064x}",
        reference=f"ISO26262-X:{index}",
        presence_confidence=1.0,
        contains_clause_or_requirement_applicability=clause,
        other_applicability_targets=other_targets,
        generator=_generator(index, v2=True),
        evidence_grounded=True,
    )
    if clause:
        return ApplicabilityDetailClauseResult(
            **common,
            outcome=ApplicabilityDetailOutcome.ENRICHED,
            applicability_target=ApplicabilityTarget.CLAUSE_OR_REQUIREMENT,
            applicability_functions=(ApplicabilityFunction.INCLUSION,),
            evidence=(
                ApplicabilityDetailEvidence(
                    function=ApplicabilityFunction.INCLUSION,
                    text="Clause applicability evidence",
                ),
            ),
        )
    target = (
        ApplicabilityTarget(other_targets[0].value) if other_targets else ApplicabilityTarget.NONE
    )
    return ApplicabilityDetailClauseResult(
        **common,
        outcome=ApplicabilityDetailOutcome.NOT_CONFIRMED,
        applicability_target=target,
    )


def _report(
    selection: ApplicabilityDetailSelection,
    *,
    v2: bool,
    clauses: tuple[ApplicabilityDetailClauseResult, ...],
) -> ApplicabilityDetailEnrichmentReport:
    enriched = sum(item.outcome is ApplicabilityDetailOutcome.ENRICHED for item in clauses)
    not_confirmed = sum(
        item.outcome is ApplicabilityDetailOutcome.NOT_CONFIRMED for item in clauses
    )
    unresolved = sum(item.outcome is ApplicabilityDetailOutcome.UNRESOLVED for item in clauses)
    failed = sum(item.outcome is ApplicabilityDetailOutcome.FAILED for item in clauses)
    return ApplicabilityDetailEnrichmentReport(
        task_version="2.0.0" if v2 else "1.0.0",
        prompt_version="detail-structure-aware-v2" if v2 else "detail-structure-aware-v1",
        model_id="qwen",
        model_ref="qwen/model",
        selection_sha256=selection.fingerprint,
        config_sha256="b" * 64 if v2 else "a" * 64,
        generated_at=NOW,
        selected_clause_count=selection.selected_clause_count,
        processed_clause_count=len(clauses),
        enriched_clause_count=enriched,
        not_confirmed_clause_count=not_confirmed,
        unresolved_clause_count=unresolved,
        failed_clause_count=failed,
        run_statistics=ApplicabilityDetailRunStatistics(
            attempted_clause_count=len(clauses),
            reused_clause_count=0,
            fresh_prediction_count=len(clauses) - failed,
            cached_prediction_count=0,
        ),
        clauses=clauses,
    )


def _fixture(tmp_path: Path) -> tuple[ApplicabilityGoldenCorpus, Path, Path]:
    presence = {1: True, 2: True, 3: True, 4: True, 5: True, 6: False}
    consensus = ConsensusReport(
        matrix_id="matrix-v6",
        corpus_id="semantic-profile-v1",
        prompt_id="applicability-presence",
        reasoning_mode_id="disabled",
        generated_at=NOW,
        model_count=3,
        clause_count=len(presence),
        categories={"unanimous": len(presence)},
        review_count=0,
        clauses=tuple(_consensus_clause(index, present=value) for index, value in presence.items()),
    )
    selected_indices = [index for index, present in presence.items() if present]
    selection = ApplicabilityDetailSelection(
        task_version="1.0.0",
        source_matrix_id=consensus.matrix_id,
        source_corpus_id=consensus.corpus_id,
        source_selection_sha256=SHA_A,
        source_consensus_sha256=_canonical_sha256(consensus.model_dump(mode="json")),
        source_coverage_sha256=SHA_C,
        source_selected_clause_count=len(presence),
        source_qualified_clause_count=len(presence),
        source_unqualified_clause_count=0,
        source_consensus_clause_count=len(presence),
        selected_clause_count=len(selected_indices),
        clauses=tuple(_selection_clause(index) for index in selected_indices),
    )

    baseline = _report(
        selection,
        v2=False,
        clauses=(
            _v1_result(1, clause=True),
            _v1_result(2, clause=False),
            _v1_result(3, clause=True),
            _v1_result(4, clause=False),
            _v1_result(5, clause=False),
        ),
    )
    candidate = _report(
        selection,
        v2=True,
        clauses=(
            _v2_result(
                1,
                clause=True,
                other_targets=(OtherApplicabilityTarget.METHOD_OR_TECHNIQUE,),
            ),
            _v2_result(
                2,
                clause=True,
                other_targets=(OtherApplicabilityTarget.METHOD_OR_TECHNIQUE,),
            ),
            _v2_result(
                3,
                clause=False,
                other_targets=(OtherApplicabilityTarget.METHOD_OR_TECHNIQUE,),
            ),
            _v2_result(4, clause=True),
            _v2_result(
                5,
                clause=False,
                other_targets=(OtherApplicabilityTarget.PROCESS_OR_ACTIVITY,),
            ),
        ),
    )

    archive_path = tmp_path / "qualification-run-073.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "inputs/applicability-detail/final-consensus-report.json",
            consensus.model_dump_json(),
        )
        archive.writestr(
            f"matrix-v6/{APPLICABILITY_DETAIL_SELECTION_FILENAME}",
            selection.model_dump_json(),
        )
        archive.writestr(
            f"matrix-v6/{APPLICABILITY_DETAIL_REPORT_FILENAME}",
            baseline.model_dump_json(),
        )

    candidate_directory = tmp_path / "detail-v2"
    candidate_directory.mkdir()
    (candidate_directory / APPLICABILITY_DETAIL_SELECTION_FILENAME).write_text(
        selection.model_dump_json(), encoding="utf-8"
    )
    (candidate_directory / APPLICABILITY_DETAIL_REPORT_FILENAME).write_text(
        candidate.model_dump_json(), encoding="utf-8"
    )

    golden = ApplicabilityGoldenCorpus(
        cases=(
            _golden_case(1, present=True),
            _golden_case(2, present=True),
            _golden_case(3, present=False),
            _golden_case(4, present=False),
            _golden_case(6, present=False),
        )
    )
    return golden, archive_path, candidate_directory


def test_comparison_reports_contract_transitions_and_metric_deltas(tmp_path: Path) -> None:
    golden, archive, candidate_directory = _fixture(tmp_path)

    report = compare_applicability_detail_contracts(
        golden,
        baseline_archive=archive,
        candidate_directory=candidate_directory,
    )

    assert report.selected_clause_count == 5
    assert report.golden_candidate_count == 4
    assert report.improvement_count == 2
    assert report.regression_count == 1
    assert report.stable_wrong_count == 0
    assert report.decision_transition_counts == {
        "clause_or_requirement_to_clause_or_requirement": 1,
        "clause_or_requirement_to_non_clause": 1,
        "non_clause_to_clause_or_requirement": 2,
        "non_clause_to_non_clause": 1,
    }
    assert report.correctness_transition_counts == {
        "correct_to_correct": 1,
        "correct_to_wrong": 1,
        "wrong_to_correct": 2,
    }
    assert report.candidate_target_pattern_counts == {
        "clause_only": 1,
        "mixed_target": 2,
        "non_clause_target": 2,
    }
    assert report.end_to_end_metrics.true_positive_delta == 1
    assert report.end_to_end_metrics.false_positive_delta == 0
    assert report.end_to_end_metrics.false_negative_delta == -1
    assert report.end_to_end_metrics.f1_delta > 0

    cases = {item.clause_id: item for item in report.cases}
    assert cases["clause-2"].correctness_transition == "wrong_to_correct"
    assert (
        cases["clause-2"].candidate_target_pattern
        is ApplicabilityCandidateTargetPattern.MIXED_TARGET
    )
    assert cases["clause-3"].decision_transition == "clause_or_requirement_to_non_clause"
    assert cases["clause-4"].correctness_transition == "correct_to_wrong"
    assert cases["clause-5"].expected_present is None
    assert cases["clause-5"].correctness_transition is None


def test_comparison_rejects_candidate_selection_drift(tmp_path: Path) -> None:
    golden, archive, candidate_directory = _fixture(tmp_path)
    selection_path = candidate_directory / APPLICABILITY_DETAIL_SELECTION_FILENAME
    payload = json.loads(selection_path.read_text(encoding="utf-8"))
    payload["clauses"][0]["presence_confidence"] = 0.9
    selection_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="selection differs from the archived baseline"):
        compare_applicability_detail_contracts(
            golden,
            baseline_archive=archive,
            candidate_directory=candidate_directory,
        )
