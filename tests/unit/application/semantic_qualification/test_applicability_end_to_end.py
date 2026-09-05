from __future__ import annotations

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
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailClauseResult,
    ApplicabilityDetailEnrichmentReport,
    ApplicabilityDetailEvidence,
    ApplicabilityDetailFailure,
    ApplicabilityDetailGenerator,
    ApplicabilityDetailOutcome,
    ApplicabilityDetailRunStatistics,
    ApplicabilityDetailSelection,
    ApplicabilityDetailSelectionClause,
)
from standards_atlas.application.semantic_qualification.applicability_end_to_end import (
    evaluate_applicability_end_to_end,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
)
from standards_atlas.domain.model import ApplicabilityFunction, ApplicabilityTarget

NOW = datetime(2026, 9, 4, tzinfo=UTC)
SHA_A = "a" * 64
SHA_C = "c" * 64


def _canonical_sha256(payload: object) -> str:
    import hashlib

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
        category="test",
        status="published",
        expected=ApplicabilityGoldenExpected(present=present),
        provenance=ApplicabilityGoldenProvenance(
            source_archive="qualification-run-071.zip",
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


def _generator(index: int) -> ApplicabilityDetailGenerator:
    return ApplicabilityDetailGenerator(
        model_id="qwen",
        model="qwen/model",
        provider="ramalama",
        task_version="1.0.0",
        prompt_version="detail-structure-aware-v1",
        input_hash=f"input-{index}",
        raw_response_hash=f"response-{index}",
        duration_ms=10,
        cached=False,
        generated_at=NOW,
    )


def _detail_result(
    index: int,
    *,
    outcome: ApplicabilityDetailOutcome,
    target: ApplicabilityTarget | None = None,
) -> ApplicabilityDetailClauseResult:
    common = dict(
        example_id=f"example-{index}",
        document_key="ISO26262-X",
        clause_id=f"clause-{index}",
        content_hash=f"sha256:{index:064x}",
        reference=f"ISO26262-X:{index}",
        presence_confidence=1.0,
        outcome=outcome,
    )
    if outcome is ApplicabilityDetailOutcome.FAILED:
        return ApplicabilityDetailClauseResult(
            **common,
            failure=ApplicabilityDetailFailure(
                error_type="TimeoutError",
                message="timeout",
                category="timeout",
            ),
        )
    if outcome is ApplicabilityDetailOutcome.NOT_CONFIRMED:
        return ApplicabilityDetailClauseResult(
            **common,
            applicability_target=target or ApplicabilityTarget.METHOD_OR_TECHNIQUE,
            evidence_grounded=True,
            generator=_generator(index),
        )
    if outcome is ApplicabilityDetailOutcome.UNRESOLVED:
        return ApplicabilityDetailClauseResult(
            **common,
            applicability_target=ApplicabilityTarget.CLAUSE_OR_REQUIREMENT,
            evidence_grounded=True,
            generator=_generator(index),
        )
    return ApplicabilityDetailClauseResult(
        **common,
        applicability_target=ApplicabilityTarget.CLAUSE_OR_REQUIREMENT,
        applicability_functions=(ApplicabilityFunction.INCLUSION,),
        evidence=(
            ApplicabilityDetailEvidence(
                function=ApplicabilityFunction.INCLUSION,
                text="Clause applicability evidence",
            ),
        ),
        evidence_grounded=True,
        generator=_generator(index),
    )


def _write_archive(tmp_path: Path, *, omit_selected_index: int | None = None) -> Path:
    presence = {
        1: True,  # true positive, retained by detail
        2: True,  # false positive, rejected by detail
        3: False,  # true negative, never enters detail
        4: True,  # true positive, detail operational failure
        5: False,  # false negative in Presence
        6: True,  # true positive, falsely rejected by detail
        7: True,  # false positive, retained by detail
    }
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
    selected_indices = [index for index, value in presence.items() if value]
    if omit_selected_index is not None:
        selected_indices.remove(omit_selected_index)
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

    results = {
        1: _detail_result(1, outcome=ApplicabilityDetailOutcome.ENRICHED),
        2: _detail_result(
            2,
            outcome=ApplicabilityDetailOutcome.NOT_CONFIRMED,
            target=ApplicabilityTarget.METHOD_OR_TECHNIQUE,
        ),
        4: _detail_result(4, outcome=ApplicabilityDetailOutcome.FAILED),
        6: _detail_result(
            6,
            outcome=ApplicabilityDetailOutcome.NOT_CONFIRMED,
            target=ApplicabilityTarget.PROCESS_OR_ACTIVITY,
        ),
        7: _detail_result(7, outcome=ApplicabilityDetailOutcome.UNRESOLVED),
    }
    selected_results = tuple(results[index] for index in selected_indices if index in results)
    outcome_counts = {outcome: 0 for outcome in ApplicabilityDetailOutcome}
    for item in selected_results:
        outcome_counts[item.outcome] += 1
    generated = sum(
        item.outcome is not ApplicabilityDetailOutcome.FAILED for item in selected_results
    )
    detail = ApplicabilityDetailEnrichmentReport(
        task_version="1.0.0",
        prompt_version="detail-structure-aware-v1",
        model_id="qwen",
        model_ref="qwen/model",
        selection_sha256=selection.fingerprint,
        config_sha256=SHA_A,
        generated_at=NOW,
        selected_clause_count=len(selected_indices),
        processed_clause_count=len(selected_results),
        enriched_clause_count=outcome_counts[ApplicabilityDetailOutcome.ENRICHED],
        not_confirmed_clause_count=outcome_counts[ApplicabilityDetailOutcome.NOT_CONFIRMED],
        unresolved_clause_count=outcome_counts[ApplicabilityDetailOutcome.UNRESOLVED],
        failed_clause_count=outcome_counts[ApplicabilityDetailOutcome.FAILED],
        run_statistics=ApplicabilityDetailRunStatistics(
            attempted_clause_count=len(selected_results),
            reused_clause_count=0,
            fresh_prediction_count=generated,
            cached_prediction_count=0,
        ),
        clauses=selected_results,
    )

    archive_path = tmp_path / "qualification-run-071.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "inputs/applicability-detail/final-consensus-report.json",
            consensus.model_dump_json(),
        )
        archive.writestr(
            "matrix-v6/applicability-detail-selection.json",
            selection.model_dump_json(),
        )
        archive.writestr(
            "matrix-v6/applicability-detail-enrichment.json",
            detail.model_dump_json(),
        )
    return archive_path


def test_end_to_end_evaluator_combines_final_presence_and_detail_verification(
    tmp_path: Path,
) -> None:
    golden = ApplicabilityGoldenCorpus(
        cases=(
            _golden_case(1, present=True),
            _golden_case(2, present=False),
            _golden_case(3, present=False),
            _golden_case(4, present=True),
            _golden_case(5, present=True),
            _golden_case(6, present=True),
            _golden_case(7, present=False),
        )
    )

    report = evaluate_applicability_end_to_end(golden, _write_archive(tmp_path))

    assert report.published_cases == 7
    assert report.matched_cases == 7
    assert report.positive_cases == 4
    assert report.negative_cases == 3

    presence = report.presence_detection
    assert presence.model_id == "final_cascade"
    assert (presence.true_positive, presence.false_positive) == (3, 2)
    assert (presence.true_negative, presence.false_negative) == (1, 1)
    assert presence.predicted_positive_cases == 5
    assert presence.presence_recall == pytest.approx(0.75)

    detail = report.detail_verification
    assert detail.source_presence_candidate_count == 5
    assert detail.golden_presence_candidate_count == 5
    assert detail.evaluated_candidate_count == 4
    assert detail.confirmed_clause_applicability_count == 2
    assert detail.rejected_non_clause_count == 2
    assert detail.failed_candidate_count == 1
    assert detail.true_positive_candidate_count == 3
    assert detail.false_positive_candidate_count == 2
    assert detail.true_positive_retained_count == 1
    assert detail.true_positive_rejected_count == 1
    assert detail.false_positive_rejected_count == 1
    assert detail.false_positive_retained_count == 1
    assert detail.failed_true_positive_count == 1
    assert detail.failed_false_positive_count == 0
    assert detail.metrics.presence_precision == pytest.approx(0.5)
    assert detail.metrics.presence_recall == pytest.approx(0.5)
    assert detail.metrics.presence_specificity == pytest.approx(0.5)
    assert detail.target_counts == {
        "clause_or_requirement": 2,
        "method_or_technique": 1,
        "process_or_activity": 1,
    }
    assert detail.outcome_counts == {
        "enriched": 1,
        "failed": 1,
        "not_confirmed": 2,
        "unresolved": 1,
    }

    end_to_end = report.end_to_end
    assert end_to_end.model_id == "end_to_end"
    assert end_to_end.evaluated_cases == 6
    assert (end_to_end.true_positive, end_to_end.false_positive) == (1, 1)
    assert (end_to_end.true_negative, end_to_end.false_negative) == (2, 2)
    assert report.end_to_end_unresolved_count == 1
    assert report.end_to_end_unresolved_cases == ("ISO26262-X/clause-4",)

    decisions = {item.clause_id: item for item in report.cases}
    assert decisions["clause-2"].applicability_target is ApplicabilityTarget.METHOD_OR_TECHNIQUE
    assert decisions["clause-2"].final_present is False
    assert decisions["clause-6"].final_error == "false_negative"
    assert decisions["clause-7"].detail_outcome is ApplicabilityDetailOutcome.UNRESOLVED
    assert decisions["clause-7"].final_present is True
    assert decisions["clause-4"].final_present is None


def test_end_to_end_evaluator_rejects_detail_selection_that_differs_from_final_presence(
    tmp_path: Path,
) -> None:
    golden = ApplicabilityGoldenCorpus(cases=(_golden_case(1, present=True),))
    archive = _write_archive(tmp_path, omit_selected_index=7)

    with pytest.raises(
        ValueError,
        match="detail selection does not match final Presence-positive consensus",
    ):
        evaluate_applicability_end_to_end(golden, archive)


def test_end_to_end_evaluator_requires_target_verification_detail_contract(tmp_path: Path) -> None:
    golden = ApplicabilityGoldenCorpus(cases=(_golden_case(1, present=True),))
    archive = _write_archive(tmp_path)
    rewritten = tmp_path / "legacy-detail.zip"
    with ZipFile(archive) as source, ZipFile(rewritten, "w", compression=ZIP_DEFLATED) as target:
        for name in source.namelist():
            payload = source.read(name)
            if name.endswith("applicability-detail-enrichment.json"):
                report = json.loads(payload)
                report["clauses"][0].pop("applicability_target")
                report["clauses"][0]["applicability_statement_confirmed"] = True
                payload = json.dumps(report).encode()
            target.writestr(name, payload)

    with pytest.raises(ValueError, match="incompatible with target verification"):
        evaluate_applicability_end_to_end(golden, rewritten)
