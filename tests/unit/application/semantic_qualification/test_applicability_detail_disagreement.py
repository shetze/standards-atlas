from __future__ import annotations

import csv
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
from standards_atlas.application.semantic_qualification.applicability_detail_disagreement import (
    ApplicabilityDetailHitlConsensusReport,
    build_applicability_detail_disagreement_review,
    evaluate_applicability_detail_hitl_consensus,
    publish_applicability_detail_disagreement_review,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    APPLICABILITY_DETAIL_REPORT_FILENAME,
    APPLICABILITY_DETAIL_SELECTION_FILENAME,
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
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
)
from standards_atlas.domain.model import ApplicabilityFunction, ApplicabilityTarget

NOW = datetime(2026, 9, 7, tzinfo=UTC)


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _selection(texts: tuple[str, ...]) -> ApplicabilityDetailSelection:
    return ApplicabilityDetailSelection(
        task_version="1.0.0",
        source_matrix_id="matrix-v6",
        source_corpus_id="semantic-profile-v1",
        source_selection_sha256="a" * 64,
        source_consensus_sha256="b" * 64,
        source_coverage_sha256="c" * 64,
        source_selected_clause_count=len(texts),
        source_qualified_clause_count=len(texts),
        source_unqualified_clause_count=0,
        source_consensus_clause_count=len(texts),
        selected_clause_count=len(texts),
        clauses=tuple(
            ApplicabilityDetailSelectionClause(
                example_id=f"example-{index}",
                document_key="DOC",
                clause_id=f"clause-{index}",
                content_hash=_hash(text),
                reference=str(index),
                heading=f"Clause {index}",
                presence_confidence=1.0,
                presence_category="unanimous",
                presence_resolution_source="final-cascade",
            )
            for index, text in enumerate(texts, start=1)
        ),
    )


def _result(
    index: int, text: str, *, decision: bool, prompt: str
) -> ApplicabilityDetailClauseResult:
    generator = ApplicabilityDetailGenerator(
        model_id="mistral",
        model="mistral/model",
        provider="ramalama",
        task_version="2.0.0",
        prompt_version=prompt,
        input_hash=f"input-{index}-{prompt}",
        raw_response_hash=f"response-{index}-{prompt}",
        duration_ms=10,
        generated_at=NOW,
    )
    common = dict(
        example_id=f"example-{index}",
        document_key="DOC",
        clause_id=f"clause-{index}",
        content_hash=_hash(text),
        reference=str(index),
        heading=f"Clause {index}",
        presence_confidence=1.0,
        contains_clause_or_requirement_applicability=decision,
        generator=generator,
        evidence_grounded=True,
    )
    if decision:
        return ApplicabilityDetailClauseResult(
            **common,
            outcome=ApplicabilityDetailOutcome.ENRICHED,
            applicability_target=ApplicabilityTarget.CLAUSE_OR_REQUIREMENT,
            applicability_functions=(ApplicabilityFunction.INCLUSION,),
            evidence=(
                ApplicabilityDetailEvidence(
                    function=ApplicabilityFunction.INCLUSION,
                    text=text,
                ),
            ),
        )
    return ApplicabilityDetailClauseResult(
        **common,
        outcome=ApplicabilityDetailOutcome.NOT_CONFIRMED,
        applicability_target=ApplicabilityTarget.NONE,
    )


def _failed_result(index: int, text: str) -> ApplicabilityDetailClauseResult:
    return ApplicabilityDetailClauseResult(
        example_id=f"example-{index}",
        document_key="DOC",
        clause_id=f"clause-{index}",
        content_hash=_hash(text),
        reference=str(index),
        heading=f"Clause {index}",
        presence_confidence=1.0,
        outcome=ApplicabilityDetailOutcome.FAILED,
        failure=ApplicabilityDetailFailure(
            error_type="LlmResponseError",
            message="finish_reason=length",
            category="invalid_response",
            finish_reason="length",
        ),
    )


def _report_from_clauses(
    selection: ApplicabilityDetailSelection,
    clauses: tuple[ApplicabilityDetailClauseResult, ...],
    *,
    prompt: str,
) -> ApplicabilityDetailEnrichmentReport:
    outcomes = {outcome: 0 for outcome in ApplicabilityDetailOutcome}
    for clause in clauses:
        outcomes[clause.outcome] += 1
    return ApplicabilityDetailEnrichmentReport(
        task_version="2.0.0",
        prompt_version=prompt,
        model_id="mistral",
        model_ref="mistral/model",
        selection_sha256=selection.fingerprint,
        config_sha256="d" * 64,
        generated_at=NOW,
        selected_clause_count=len(clauses),
        processed_clause_count=len(clauses),
        enriched_clause_count=outcomes[ApplicabilityDetailOutcome.ENRICHED],
        not_confirmed_clause_count=outcomes[ApplicabilityDetailOutcome.NOT_CONFIRMED],
        unresolved_clause_count=outcomes[ApplicabilityDetailOutcome.UNRESOLVED],
        failed_clause_count=outcomes[ApplicabilityDetailOutcome.FAILED],
        run_statistics=ApplicabilityDetailRunStatistics(
            attempted_clause_count=len(clauses),
            reused_clause_count=0,
            fresh_prediction_count=len(clauses),
            cached_prediction_count=0,
        ),
        clauses=clauses,
    )


def _report(
    selection: ApplicabilityDetailSelection,
    texts: tuple[str, ...],
    *,
    decisions: tuple[bool, ...],
    prompt: str,
) -> ApplicabilityDetailEnrichmentReport:
    clauses = tuple(
        _result(index, text, decision=decision, prompt=prompt)
        for index, (text, decision) in enumerate(zip(texts, decisions, strict=True), start=1)
    )
    return ApplicabilityDetailEnrichmentReport(
        task_version="2.0.0",
        prompt_version=prompt,
        model_id="mistral",
        model_ref="mistral/model",
        selection_sha256=selection.fingerprint,
        config_sha256="d" * 64,
        generated_at=NOW,
        selected_clause_count=len(clauses),
        processed_clause_count=len(clauses),
        enriched_clause_count=sum(decisions),
        not_confirmed_clause_count=len(decisions) - sum(decisions),
        unresolved_clause_count=0,
        failed_clause_count=0,
        run_statistics=ApplicabilityDetailRunStatistics(
            attempted_clause_count=len(clauses),
            reused_clause_count=0,
            fresh_prediction_count=len(clauses),
            cached_prediction_count=0,
        ),
        clauses=clauses,
    )


def _candidate_directory(
    root: Path,
    selection: ApplicabilityDetailSelection,
    report: ApplicabilityDetailEnrichmentReport,
) -> Path:
    root.mkdir()
    (root / APPLICABILITY_DETAIL_SELECTION_FILENAME).write_text(
        selection.model_dump_json(indent=2) + "\n"
    )
    (root / APPLICABILITY_DETAIL_REPORT_FILENAME).write_text(
        report.model_dump_json(indent=2) + "\n"
    )
    return root


def _archive(path: Path, texts: tuple[str, ...]) -> Path:
    dataset = {
        "task": "qualification",
        "version": "1",
        "examples": [
            {
                "id": f"example-{index}",
                "input": {
                    "context": {"document_key": "DOC", "clause_id": f"clause-{index}"},
                    "content": {"text": text},
                },
                "expected": {},
            }
            for index, text in enumerate(texts, start=1)
        ],
    }
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("inputs/corpus/dataset.json", json.dumps(dataset))
    return path


def _empty_golden() -> ApplicabilityGoldenCorpus:
    return ApplicabilityGoldenCorpus(cases=())


def _golden_for(
    texts: tuple[str, ...],
    *,
    decisions: dict[int, bool],
) -> ApplicabilityGoldenCorpus:
    return ApplicabilityGoldenCorpus(
        cases=tuple(
            ApplicabilityGoldenCase(
                clause_id=f"clause-{index}",
                document_key="DOC",
                reference=str(index),
                text=texts[index - 1],
                category="test",
                status="published",
                expected=ApplicabilityGoldenExpected(present=decision),
                provenance=ApplicabilityGoldenProvenance(
                    source_archive="run.zip",
                    source_archive_sha256="a" * 64,
                ),
            )
            for index, decision in decisions.items()
        )
    )


def _fixture(tmp_path: Path):
    texts = ("Clause one applies when X.", "Clause two applies always.")
    selection = _selection(texts)
    left = _candidate_directory(
        tmp_path / "left",
        selection,
        _report(selection, texts, decisions=(True, False), prompt="detail-structure-aware-v3"),
    )
    right = _candidate_directory(
        tmp_path / "right",
        selection,
        _report(selection, texts, decisions=(False, False), prompt="detail-structure-aware-v4"),
    )
    return texts, selection, left, right, _archive(tmp_path / "run.zip", texts)


def test_build_creates_review_only_for_primary_disagreements(tmp_path: Path) -> None:
    _, selection, left, right, archive = _fixture(tmp_path)
    review = tmp_path / "review" / "disagreement.csv"

    result = build_applicability_detail_disagreement_review(
        golden=_empty_golden(),
        run_archive=archive,
        left_directory=left,
        right_directory=right,
        review_path=review,
    )

    assert result.selected_clause_count == 2
    assert result.agreement_count == 1
    assert result.disagreement_count == 1
    rows = list(csv.DictReader(review.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["clause_id"] == "clause-1"
    assert rows[0]["left_decision"] == "true"
    assert rows[0]["right_decision"] == "false"
    assert rows[0]["selection_sha256"] == selection.fingerprint
    assert "Clause one applies when X." in rows[0]["text"]
    assert (review.parent / "README.md").is_file()


def test_review_places_editable_columns_immediately_after_clause_identity(tmp_path: Path) -> None:
    _, _, left, right, archive = _fixture(tmp_path)
    review = tmp_path / "review" / "disagreement.csv"

    build_applicability_detail_disagreement_review(
        golden=_empty_golden(),
        run_archive=archive,
        left_directory=left,
        right_directory=right,
        review_path=review,
    )

    with review.open(encoding="utf-8", newline="") as handle:
        fieldnames = tuple(csv.DictReader(handle).fieldnames or ())
    assert fieldnames[:6] == (
        "document_key",
        "reference",
        "heading",
        "review_status",
        "contains_clause_or_requirement_applicability",
        "review_note",
    )


def test_build_excludes_published_golden_disagreement_from_hitl(tmp_path: Path) -> None:
    texts, _, left, right, archive = _fixture(tmp_path)
    review = tmp_path / "review" / "disagreement.csv"
    golden = _golden_for(texts, decisions={1: True})

    result = build_applicability_detail_disagreement_review(
        golden=golden,
        run_archive=archive,
        left_directory=left,
        right_directory=right,
        review_path=review,
    )

    assert result.disagreement_count == 1
    assert result.golden_auto_resolved_count == 1
    assert result.new_hitl_count == 0
    rows = list(csv.DictReader(review.open(encoding="utf-8")))
    assert rows == []

    consensus = publish_applicability_detail_disagreement_review(
        golden=golden,
        review_path=review,
        run_archive=archive,
        left_directory=left,
        right_directory=right,
        output_path=tmp_path / "consensus.json",
    )
    assert consensus.golden_auto_resolved_count == 1
    assert consensus.hitl_review_count == 0
    first = consensus.clauses[0]
    assert first.resolution_source.value == "golden"
    assert first.golden_decision is True
    assert first.final_decision is True


def test_build_rejects_stale_golden_text_for_auto_resolution(tmp_path: Path) -> None:
    texts, _, left, right, archive = _fixture(tmp_path)
    stale = ApplicabilityGoldenCorpus(
        cases=(
            ApplicabilityGoldenCase(
                clause_id="clause-1",
                document_key="DOC",
                reference="1",
                text="Changed clause text.",
                category="test",
                status="published",
                expected=ApplicabilityGoldenExpected(present=True),
                provenance=ApplicabilityGoldenProvenance(
                    source_archive="run.zip",
                    source_archive_sha256="a" * 64,
                ),
            ),
        )
    )

    with pytest.raises(ValueError, match="published Golden text differs"):
        build_applicability_detail_disagreement_review(
            golden=stale,
            run_archive=archive,
            left_directory=left,
            right_directory=right,
            review_path=tmp_path / "review.csv",
        )


def test_build_excludes_source_failure_from_hitl(tmp_path: Path) -> None:
    texts = ("Clause one applies when X.", "Clause two applies always.")
    selection = _selection(texts)
    left_report = _report_from_clauses(
        selection,
        (
            _failed_result(1, texts[0]),
            _result(2, texts[1], decision=False, prompt="detail-structure-aware-v3"),
        ),
        prompt="detail-structure-aware-v3",
    )
    right_report = _report(
        selection,
        texts,
        decisions=(True, False),
        prompt="detail-structure-aware-v4",
    )
    left = _candidate_directory(tmp_path / "left", selection, left_report)
    right = _candidate_directory(tmp_path / "right", selection, right_report)
    archive = _archive(tmp_path / "run.zip", texts)
    review = tmp_path / "review" / "disagreement.csv"

    result = build_applicability_detail_disagreement_review(
        golden=_empty_golden(),
        run_archive=archive,
        left_directory=left,
        right_directory=right,
        review_path=review,
    )

    assert result.agreement_count == 1
    assert result.disagreement_count == 0
    assert result.new_hitl_count == 0
    assert result.source_failure_count == 1
    assert list(csv.DictReader(review.open(encoding="utf-8"))) == []

    consensus = publish_applicability_detail_disagreement_review(
        golden=_empty_golden(),
        review_path=review,
        run_archive=archive,
        left_directory=left,
        right_directory=right,
        output_path=tmp_path / "consensus.json",
    )
    assert consensus.source_failure_count == 1
    assert consensus.clauses[0].resolution_source.value == "source_failure"
    assert consensus.clauses[0].final_decision is None


def test_publish_merges_automatic_agreement_and_hitl_decision(tmp_path: Path) -> None:
    _, _, left, right, archive = _fixture(tmp_path)
    review = tmp_path / "review" / "disagreement.csv"
    build_applicability_detail_disagreement_review(
        golden=_empty_golden(),
        run_archive=archive,
        left_directory=left,
        right_directory=right,
        review_path=review,
    )
    rows = list(csv.DictReader(review.open(encoding="utf-8")))
    rows[0]["review_status"] = "published"
    rows[0]["contains_clause_or_requirement_applicability"] = "true"
    rows[0]["review_note"] = "Human confirms normative gate."
    with review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    output = tmp_path / "consensus.json"
    report = publish_applicability_detail_disagreement_review(
        golden=_empty_golden(),
        review_path=review,
        run_archive=archive,
        left_directory=left,
        right_directory=right,
        output_path=output,
    )

    assert report.automatic_agreement_count == 1
    assert report.hitl_resolved_count == 1
    assert report.pending_count == 0
    assert report.final_positive_count == 1
    assert report.final_negative_count == 1
    persisted = ApplicabilityDetailHitlConsensusReport.model_validate_json(output.read_text())
    assert persisted.clauses[0].final_decision is True
    assert persisted.clauses[1].final_decision is False


def test_publish_rejects_stale_review_provenance(tmp_path: Path) -> None:
    _, _, left, right, archive = _fixture(tmp_path)
    review = tmp_path / "review" / "disagreement.csv"
    build_applicability_detail_disagreement_review(
        golden=_empty_golden(),
        run_archive=archive,
        left_directory=left,
        right_directory=right,
        review_path=review,
    )
    rows = list(csv.DictReader(review.open(encoding="utf-8")))
    rows[0]["left_prompt_version"] = "tampered"
    with review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="source/provenance changed"):
        publish_applicability_detail_disagreement_review(
            golden=_empty_golden(),
            review_path=review,
            run_archive=archive,
            left_directory=left,
            right_directory=right,
            output_path=tmp_path / "consensus.json",
        )


def test_evaluate_uses_presence_then_hitl_detail(monkeypatch, tmp_path: Path) -> None:
    _, selection, left, right, archive = _fixture(tmp_path)
    review = tmp_path / "review" / "disagreement.csv"
    build_applicability_detail_disagreement_review(
        golden=_empty_golden(),
        run_archive=archive,
        left_directory=left,
        right_directory=right,
        review_path=review,
    )
    rows = list(csv.DictReader(review.open(encoding="utf-8")))
    rows[0]["review_status"] = "published"
    rows[0]["contains_clause_or_requirement_applicability"] = "true"
    with review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    consensus_path = tmp_path / "consensus.json"
    publish_applicability_detail_disagreement_review(
        golden=_empty_golden(),
        review_path=review,
        run_archive=archive,
        left_directory=left,
        right_directory=right,
        output_path=consensus_path,
    )

    presence = ConsensusReport(
        matrix_id="matrix-v6",
        corpus_id="semantic-profile-v1",
        prompt_id="presence",
        reasoning_mode_id="disabled",
        generated_at=NOW,
        model_count=3,
        clause_count=2,
        categories={"unanimous": 2},
        review_count=0,
        clauses=(
            ClauseConsensus(
                clause_id="clause-1",
                document_key="DOC",
                reference="1",
                category=ConsensusCategory.UNANIMOUS,
                applicability_category=ConsensusCategory.UNANIMOUS,
                applicability_present=True,
                applicability_presence_confidence=1.0,
                confidence=1.0,
                participating_models=3,
                requires_review=False,
            ),
            ClauseConsensus(
                clause_id="clause-2",
                document_key="DOC",
                reference="2",
                category=ConsensusCategory.UNANIMOUS,
                applicability_category=ConsensusCategory.UNANIMOUS,
                applicability_present=False,
                applicability_presence_confidence=1.0,
                confidence=1.0,
                participating_models=3,
                requires_review=False,
            ),
        ),
    )
    from standards_atlas.application.semantic_qualification import (
        applicability_detail_disagreement as module,
    )

    monkeypatch.setattr(
        module,
        "load_applicability_end_to_end_artifacts",
        lambda _: (presence, selection, object()),
    )
    golden = ApplicabilityGoldenCorpus(
        cases=(
            ApplicabilityGoldenCase(
                clause_id="clause-1",
                document_key="DOC",
                reference="1",
                text="Clause one",
                category="test",
                status="published",
                expected=ApplicabilityGoldenExpected(present=True),
                provenance=ApplicabilityGoldenProvenance(
                    source_archive="run.zip", source_archive_sha256="a" * 64
                ),
            ),
            ApplicabilityGoldenCase(
                clause_id="clause-2",
                document_key="DOC",
                reference="2",
                text="Clause two",
                category="test",
                status="published",
                expected=ApplicabilityGoldenExpected(present=False),
                provenance=ApplicabilityGoldenProvenance(
                    source_archive="run.zip", source_archive_sha256="a" * 64
                ),
            ),
        )
    )

    report = evaluate_applicability_detail_hitl_consensus(
        golden,
        baseline_archive=archive,
        consensus_path=consensus_path,
    )

    assert report.metrics.true_positive == 1
    assert report.metrics.true_negative == 1
    assert report.metrics.false_positive == 0
    assert report.metrics.false_negative == 0
