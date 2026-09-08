"""HITL resolution of applicability-detail prompt disagreements."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from zipfile import ZipFile

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCase,
    ApplicabilityGoldenCorpus,
    ApplicabilityGoldenExpected,
    ApplicabilityModelMetrics,
    _metrics,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    APPLICABILITY_DETAIL_REPORT_FILENAME,
    APPLICABILITY_DETAIL_SELECTION_FILENAME,
    ApplicabilityDetailClauseResult,
    ApplicabilityDetailEnrichmentReport,
    ApplicabilityDetailOutcome,
    ApplicabilityDetailSelection,
    load_applicability_detail_report,
    load_applicability_detail_selection,
)
from standards_atlas.application.semantic_qualification.applicability_end_to_end import (
    load_applicability_end_to_end_artifacts,
)
from standards_atlas.application.semantic_qualification.applicability_hard_cases import _find_member
from standards_atlas.domain.model import ApplicabilityTarget


class ApplicabilityDetailDisagreementKind(StrEnum):
    """Reason why two detail arms need human adjudication."""

    DECISION = "decision"
    LEFT_FAILED = "left_failed"
    RIGHT_FAILED = "right_failed"
    BOTH_FAILED = "both_failed"


class ApplicabilityDetailResolutionSource(StrEnum):
    """Source of one final dual-decision Boolean."""

    AUTOMATIC_AGREEMENT = "automatic_agreement"
    GOLDEN = "golden"
    HITL = "hitl"
    PENDING = "pending"
    SOURCE_FAILURE = "source_failure"


class ApplicabilityDetailDisagreementBuildResult(BaseModel):
    """Paths and counts emitted by the HITL review builder."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_path: Path
    review_guide_path: Path
    selected_clause_count: int = Field(ge=0)
    agreement_count: int = Field(ge=0)
    disagreement_count: int = Field(ge=0)
    golden_auto_resolved_count: int = Field(ge=0)
    new_hitl_count: int = Field(ge=0)
    source_failure_count: int = Field(ge=0)
    review_created: bool


class ApplicabilityDetailHitlConsensusCase(BaseModel):
    """Resolved or pending decision for one Presence-positive detail candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    reference: str | None = None
    heading: str | None = None
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    presence_confidence: float = Field(ge=0.0, le=1.0)
    left_decision: bool | None = None
    right_decision: bool | None = None
    disagreement_kind: ApplicabilityDetailDisagreementKind | None = None
    review_status: Literal["published", "pending"] | None = None
    golden_decision: bool | None = None
    hitl_decision: bool | None = None
    review_note: str = ""
    final_decision: bool | None = None
    resolution_source: ApplicabilityDetailResolutionSource

    @model_validator(mode="after")
    def validate_resolution(self) -> ApplicabilityDetailHitlConsensusCase:
        if self.resolution_source is ApplicabilityDetailResolutionSource.AUTOMATIC_AGREEMENT:
            if self.disagreement_kind is not None:
                raise ValueError("automatic agreement cannot have disagreement_kind")
            if self.left_decision is None or self.left_decision != self.right_decision:
                raise ValueError("automatic agreement requires equal resolved arm decisions")
            if self.final_decision != self.left_decision:
                raise ValueError("automatic agreement final decision must equal both arms")
            if self.hitl_decision is not None or self.review_status is not None:
                raise ValueError("automatic agreement must not contain HITL fields")
        elif self.resolution_source is ApplicabilityDetailResolutionSource.GOLDEN:
            if self.disagreement_kind is None:
                raise ValueError("Golden resolution requires a disagreement_kind")
            if self.golden_decision is None or self.final_decision != self.golden_decision:
                raise ValueError("Golden final decision must equal the published Golden decision")
            if self.hitl_decision is not None or self.review_status is not None:
                raise ValueError("Golden resolution must not contain HITL fields")
        elif self.resolution_source is ApplicabilityDetailResolutionSource.HITL:
            if self.disagreement_kind is not ApplicabilityDetailDisagreementKind.DECISION:
                raise ValueError("HITL resolution requires a semantic decision disagreement")
            if self.review_status != "published" or self.hitl_decision is None:
                raise ValueError("HITL resolution requires a published human decision")
            if self.final_decision != self.hitl_decision:
                raise ValueError("HITL final decision must equal the human decision")
        elif self.resolution_source is ApplicabilityDetailResolutionSource.PENDING:
            if self.disagreement_kind is not ApplicabilityDetailDisagreementKind.DECISION:
                raise ValueError("pending resolution requires a semantic decision disagreement")
            if self.final_decision is not None or self.hitl_decision is not None:
                raise ValueError("pending resolution must not contain a final decision")
            if self.review_status not in {None, "pending"}:
                raise ValueError("pending resolution must have pending review status")
        else:
            if self.disagreement_kind in {None, ApplicabilityDetailDisagreementKind.DECISION}:
                raise ValueError("source failure resolution requires a technical arm failure")
            if self.final_decision is not None:
                raise ValueError("source failure must remain unresolved")
            if (
                self.golden_decision is not None
                or self.hitl_decision is not None
                or self.review_status is not None
            ):
                raise ValueError("source failure must not contain Golden or HITL fields")
        return self


class ApplicabilityDetailHitlConsensusReport(BaseModel):
    """HITL-aware consensus across two exact-selection applicability-detail arms."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.1"] = "1.1"
    source_archive: str = Field(min_length=1)
    source_archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_clause_count: int = Field(ge=0)
    left_task_version: str = Field(min_length=1)
    left_prompt_version: str = Field(min_length=1)
    left_model_id: str = Field(min_length=1)
    left_model_ref: str = Field(min_length=1)
    left_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    right_task_version: str = Field(min_length=1)
    right_prompt_version: str = Field(min_length=1)
    right_model_id: str = Field(min_length=1)
    right_model_ref: str = Field(min_length=1)
    right_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    golden_corpus_id: str = Field(min_length=1)
    golden_corpus_version: str = Field(min_length=1)
    automatic_agreement_count: int = Field(ge=0)
    disagreement_count: int = Field(ge=0)
    golden_auto_resolved_count: int = Field(ge=0)
    hitl_review_count: int = Field(ge=0)
    hitl_resolved_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    source_failure_count: int = Field(ge=0)
    final_positive_count: int = Field(ge=0)
    final_negative_count: int = Field(ge=0)
    clauses: tuple[ApplicabilityDetailHitlConsensusCase, ...]

    @model_validator(mode="after")
    def validate_accounting(self) -> ApplicabilityDetailHitlConsensusReport:
        if len(self.clauses) != self.selected_clause_count:
            raise ValueError("HITL consensus clause count must match selected_clause_count")
        if (
            self.automatic_agreement_count + self.disagreement_count + self.source_failure_count
            != self.selected_clause_count
        ):
            raise ValueError("HITL agreement/disagreement/failure accounting does not balance")
        if self.golden_auto_resolved_count + self.hitl_review_count != self.disagreement_count:
            raise ValueError("Golden/HITL disagreement accounting does not balance")
        if self.hitl_resolved_count + self.pending_count != self.hitl_review_count:
            raise ValueError("HITL resolved/pending accounting does not balance")
        if (
            self.final_positive_count
            + self.final_negative_count
            + self.pending_count
            + self.source_failure_count
            != len(self.clauses)
        ):
            raise ValueError("HITL final decision accounting does not balance")
        return self


class ApplicabilityDetailHitlEvaluationCase(BaseModel):
    """Golden-set trace for one final Presence plus HITL-detail decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    expected_present: bool
    presence_present: bool
    detail_decision: bool | None = None
    resolution_source: ApplicabilityDetailResolutionSource | None = None
    final_present: bool | None = None
    final_error: Literal["false_positive", "false_negative"] | None = None


class ApplicabilityDetailHitlEvaluationReport(BaseModel):
    """End-to-end evaluation of Presence followed by v3/v4 HITL consensus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    golden_corpus_id: str = Field(min_length=1)
    golden_corpus_version: str = Field(min_length=1)
    source_matrix_id: str = Field(min_length=1)
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_cases: int = Field(ge=0)
    matched_cases: int = Field(ge=0)
    missing_cases: tuple[str, ...] = ()
    unresolved_count: int = Field(ge=0)
    metrics: ApplicabilityModelMetrics
    cases: tuple[ApplicabilityDetailHitlEvaluationCase, ...]

    @model_validator(mode="after")
    def validate_accounting(self) -> ApplicabilityDetailHitlEvaluationReport:
        if len(self.cases) != self.matched_cases:
            raise ValueError("HITL evaluation case count must match matched_cases")
        if self.matched_cases + len(self.missing_cases) != self.published_cases:
            raise ValueError("HITL evaluation matched/missing accounting does not balance")
        if self.metrics.evaluated_cases + self.unresolved_count != self.matched_cases:
            raise ValueError("HITL evaluation resolved/unresolved accounting does not balance")
        return self


_REVIEW_FIELDS = (
    "document_key",
    "reference",
    "heading",
    "review_status",
    "contains_clause_or_requirement_applicability",
    "review_note",
    "clause_id",
    "content_hash",
    "presence_confidence",
    "selection_sha256",
    "source_archive",
    "source_archive_sha256",
    "disagreement_kind",
    "left_model_id",
    "left_prompt_version",
    "left_report_sha256",
    "left_decision",
    "left_outcome",
    "left_other_targets",
    "left_functions",
    "left_evidence",
    "right_model_id",
    "right_prompt_version",
    "right_report_sha256",
    "right_decision",
    "right_outcome",
    "right_other_targets",
    "right_functions",
    "right_evidence",
    "text",
)


def build_applicability_detail_disagreement_review(
    *,
    golden: ApplicabilityGoldenCorpus,
    run_archive: Path,
    left_directory: Path,
    right_directory: Path,
    review_path: Path,
) -> ApplicabilityDetailDisagreementBuildResult:
    """Create a flat HITL CSV only for new semantic v3/v4 gate disagreements."""

    left_selection, left_report = _load_candidate(left_directory)
    right_selection, right_report = _load_candidate(right_directory)
    _validate_pair(left_selection, left_report, right_selection, right_report)
    source_text = _load_dataset_text(run_archive)
    golden_by = _published_golden_by_coordinate(golden)
    archive_sha = _file_sha256(run_archive)
    left_sha = _file_sha256(left_directory / APPLICABILITY_DETAIL_REPORT_FILENAME)
    right_sha = _file_sha256(right_directory / APPLICABILITY_DETAIL_REPORT_FILENAME)
    left_by = _by_coordinate(left_report, "left")
    right_by = _by_coordinate(right_report, "right")

    rows: list[dict[str, str]] = []
    agreement_count = 0
    semantic_disagreement_count = 0
    golden_resolved_count = 0
    failure_count = 0
    for selected in left_selection.clauses:
        coordinate = (selected.document_key, selected.clause_id)
        left = left_by[coordinate]
        right = right_by[coordinate]
        kind = _disagreement_kind(left, right)
        if kind is None:
            agreement_count += 1
            continue
        if kind is not ApplicabilityDetailDisagreementKind.DECISION:
            failure_count += 1
            continue

        semantic_disagreement_count += 1
        golden_case = golden_by.get(coordinate)
        if golden_case is not None:
            text = source_text.get(coordinate)
            if text is None:
                raise ValueError(
                    "qualification archive is missing Golden-matched clause text for "
                    f"{selected.document_key}/{selected.clause_id}"
                )
            _validate_golden_resolution(golden_case, selected=selected, source_text=text)
            golden_resolved_count += 1
            continue

        text = source_text.get(coordinate)
        if text is None:
            raise ValueError(
                "qualification archive is missing selected clause text for "
                f"{selected.document_key}/{selected.clause_id}"
            )
        calculated_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        if calculated_hash != selected.content_hash:
            raise ValueError(
                "qualification archive clause text differs from persisted detail selection for "
                f"{selected.document_key}/{selected.clause_id}"
            )
        rows.append(
            _review_row(
                selected=selected,
                text=text,
                selection_sha256=left_selection.fingerprint,
                source_archive=run_archive.name,
                source_archive_sha256=archive_sha,
                kind=kind,
                left=left,
                right=right,
                left_report=left_report,
                right_report=right_report,
                left_report_sha256=left_sha,
                right_report_sha256=right_sha,
            )
        )

    review_path.parent.mkdir(parents=True, exist_ok=True)
    created = _write_or_preserve_review(review_path, rows)
    guide = review_path.parent / "README.md"
    _write_review_guide(
        guide,
        left_report=left_report,
        right_report=right_report,
        golden=golden,
        selected_clause_count=left_selection.selected_clause_count,
        agreement_count=agreement_count,
        disagreement_count=semantic_disagreement_count,
        golden_auto_resolved_count=golden_resolved_count,
        new_hitl_count=len(rows),
        source_failure_count=failure_count,
    )
    return ApplicabilityDetailDisagreementBuildResult(
        review_path=review_path,
        review_guide_path=guide,
        selected_clause_count=left_selection.selected_clause_count,
        agreement_count=agreement_count,
        disagreement_count=semantic_disagreement_count,
        golden_auto_resolved_count=golden_resolved_count,
        new_hitl_count=len(rows),
        source_failure_count=failure_count,
        review_created=created,
    )


def publish_applicability_detail_disagreement_review(
    *,
    golden: ApplicabilityGoldenCorpus,
    review_path: Path,
    run_archive: Path,
    left_directory: Path,
    right_directory: Path,
    output_path: Path,
) -> ApplicabilityDetailHitlConsensusReport:
    """Merge agreements, existing Golden decisions, and new HITL decisions into consensus."""

    left_selection, left_report = _load_candidate(left_directory)
    right_selection, right_report = _load_candidate(right_directory)
    _validate_pair(left_selection, left_report, right_selection, right_report)
    source_text = _load_dataset_text(run_archive)
    golden_by = _published_golden_by_coordinate(golden)
    archive_sha = _file_sha256(run_archive)
    left_report_path = left_directory / APPLICABILITY_DETAIL_REPORT_FILENAME
    right_report_path = right_directory / APPLICABILITY_DETAIL_REPORT_FILENAME
    left_sha = _file_sha256(left_report_path)
    right_sha = _file_sha256(right_report_path)
    review_rows = _load_review_rows(review_path)
    left_by = _by_coordinate(left_report, "left")
    right_by = _by_coordinate(right_report, "right")

    expected_review_coordinates: set[tuple[str, str]] = set()
    for selected in left_selection.clauses:
        coordinate = (selected.document_key, selected.clause_id)
        kind = _disagreement_kind(left_by[coordinate], right_by[coordinate])
        if kind is ApplicabilityDetailDisagreementKind.DECISION and coordinate not in golden_by:
            expected_review_coordinates.add(coordinate)
    if set(review_rows) != expected_review_coordinates:
        raise ValueError(
            "HITL review coordinates differ from the current new semantic disagreements; "
            "rebuild the review from the exact candidate reports and Golden corpus"
        )

    cases: list[ApplicabilityDetailHitlConsensusCase] = []
    source_counts: Counter[ApplicabilityDetailResolutionSource] = Counter()
    semantic_disagreements = 0
    positives = negatives = 0

    for selected in left_selection.clauses:
        coordinate = (selected.document_key, selected.clause_id)
        left = left_by[coordinate]
        right = right_by[coordinate]
        kind = _disagreement_kind(left, right)
        left_decision = _detail_decision(left)
        right_decision = _detail_decision(right)
        review_status = None
        golden_decision = None
        hitl_decision = None
        note = ""

        if kind is None:
            assert left_decision is not None and left_decision == right_decision
            final = left_decision
            source = ApplicabilityDetailResolutionSource.AUTOMATIC_AGREEMENT
        elif kind is not ApplicabilityDetailDisagreementKind.DECISION:
            final = None
            source = ApplicabilityDetailResolutionSource.SOURCE_FAILURE
        else:
            semantic_disagreements += 1
            golden_case = golden_by.get(coordinate)
            if golden_case is not None:
                text = source_text.get(coordinate)
                if text is None:
                    raise ValueError(
                        "qualification archive is missing Golden-matched clause text for "
                        f"{selected.document_key}/{selected.clause_id}"
                    )
                _validate_golden_resolution(golden_case, selected=selected, source_text=text)
                expected = golden_case.expected
                assert expected is not None
                golden_decision = expected.present
                final = golden_decision
                source = ApplicabilityDetailResolutionSource.GOLDEN
            else:
                row = review_rows[coordinate]
                _validate_review_row(
                    row,
                    selected=selected,
                    selection_sha256=left_selection.fingerprint,
                    source_archive=run_archive.name,
                    source_archive_sha256=archive_sha,
                    source_text=source_text[coordinate],
                    kind=kind,
                    left=left,
                    right=right,
                    left_report=left_report,
                    right_report=right_report,
                    left_report_sha256=left_sha,
                    right_report_sha256=right_sha,
                )
                review_status = (row.get("review_status") or "pending").strip().lower()
                if review_status not in {"pending", "published"}:
                    raise ValueError(
                        f"unsupported review_status {review_status!r} for "
                        f"{selected.document_key}/{selected.clause_id}"
                    )
                if review_status == "published":
                    hitl_decision = _parse_bool_required(
                        row.get("contains_clause_or_requirement_applicability"),
                        coordinate=coordinate,
                    )
                    final = hitl_decision
                    source = ApplicabilityDetailResolutionSource.HITL
                else:
                    if (row.get("contains_clause_or_requirement_applicability") or "").strip():
                        raise ValueError(
                            "pending HITL rows must leave the decision empty for "
                            f"{selected.document_key}/{selected.clause_id}"
                        )
                    final = None
                    source = ApplicabilityDetailResolutionSource.PENDING
                note = row.get("review_note") or ""

        source_counts[source] += 1
        if final is True:
            positives += 1
        elif final is False:
            negatives += 1
        cases.append(
            ApplicabilityDetailHitlConsensusCase(
                document_key=selected.document_key,
                clause_id=selected.clause_id,
                reference=selected.reference,
                heading=selected.heading,
                content_hash=selected.content_hash,
                presence_confidence=selected.presence_confidence,
                left_decision=left_decision,
                right_decision=right_decision,
                disagreement_kind=kind,
                review_status=review_status,
                golden_decision=golden_decision,
                hitl_decision=hitl_decision,
                review_note=note,
                final_decision=final,
                resolution_source=source,
            )
        )

    report = ApplicabilityDetailHitlConsensusReport(
        source_archive=run_archive.name,
        source_archive_sha256=archive_sha,
        selection_sha256=left_selection.fingerprint,
        selected_clause_count=left_selection.selected_clause_count,
        left_task_version=left_report.task_version,
        left_prompt_version=left_report.prompt_version,
        left_model_id=left_report.model_id,
        left_model_ref=left_report.model_ref,
        left_report_sha256=left_sha,
        right_task_version=right_report.task_version,
        right_prompt_version=right_report.prompt_version,
        right_model_id=right_report.model_id,
        right_model_ref=right_report.model_ref,
        right_report_sha256=right_sha,
        golden_corpus_id=golden.corpus_id,
        golden_corpus_version=golden.corpus_version,
        automatic_agreement_count=source_counts[
            ApplicabilityDetailResolutionSource.AUTOMATIC_AGREEMENT
        ],
        disagreement_count=semantic_disagreements,
        golden_auto_resolved_count=source_counts[ApplicabilityDetailResolutionSource.GOLDEN],
        hitl_review_count=(
            source_counts[ApplicabilityDetailResolutionSource.HITL]
            + source_counts[ApplicabilityDetailResolutionSource.PENDING]
        ),
        hitl_resolved_count=source_counts[ApplicabilityDetailResolutionSource.HITL],
        pending_count=source_counts[ApplicabilityDetailResolutionSource.PENDING],
        source_failure_count=source_counts[ApplicabilityDetailResolutionSource.SOURCE_FAILURE],
        final_positive_count=positives,
        final_negative_count=negatives,
        clauses=tuple(cases),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return report


def evaluate_applicability_detail_hitl_consensus(
    golden: ApplicabilityGoldenCorpus,
    *,
    baseline_archive: Path,
    consensus_path: Path,
) -> ApplicabilityDetailHitlEvaluationReport:
    """Evaluate final Presence plus HITL-resolved detail decisions without inference."""

    detail_consensus = ApplicabilityDetailHitlConsensusReport.model_validate_json(
        consensus_path.read_text(encoding="utf-8")
    )
    presence_consensus, baseline_selection, _ = load_applicability_end_to_end_artifacts(
        baseline_archive
    )
    if detail_consensus.source_archive_sha256 != _file_sha256(baseline_archive):
        raise ValueError("HITL consensus was published from a different qualification archive")
    if detail_consensus.selection_sha256 != baseline_selection.fingerprint:
        raise ValueError("HITL consensus does not belong to the archived detail selection")
    published = tuple(
        case for case in golden.cases if case.status == "published" and case.expected is not None
    )
    if not published:
        raise ValueError("applicability golden corpus contains no published cases")
    presence_by = {(item.document_key, item.clause_id): item for item in presence_consensus.clauses}
    detail_by = {(item.document_key, item.clause_id): item for item in detail_consensus.clauses}
    predictions: list[tuple[bool, ApplicabilityGoldenExpected]] = []
    cases: list[ApplicabilityDetailHitlEvaluationCase] = []
    missing: list[str] = []
    unresolved = 0

    for case in published:
        coordinate = (case.document_key, case.clause_id)
        presence = presence_by.get(coordinate)
        if presence is None:
            missing.append(f"{case.document_key}/{case.clause_id}")
            continue
        expected = case.expected
        assert expected is not None
        if not presence.applicability_present:
            final: bool | None = False
            detail_decision = None
            source = None
        else:
            detail = detail_by.get(coordinate)
            if detail is None:
                raise ValueError(
                    "Presence-positive golden case is missing from HITL detail consensus: "
                    f"{case.document_key}/{case.clause_id}"
                )
            detail_decision = detail.final_decision
            source = detail.resolution_source
            final = detail_decision
        if final is None:
            unresolved += 1
        else:
            predictions.append((final, expected))
        error = None
        if final is not None and final != expected.present:
            error = "false_negative" if expected.present else "false_positive"
        cases.append(
            ApplicabilityDetailHitlEvaluationCase(
                document_key=case.document_key,
                clause_id=case.clause_id,
                reference=case.reference,
                expected_present=expected.present,
                presence_present=presence.applicability_present,
                detail_decision=detail_decision,
                resolution_source=source,
                final_present=final,
                final_error=error,
            )
        )

    return ApplicabilityDetailHitlEvaluationReport(
        golden_corpus_id=golden.corpus_id,
        golden_corpus_version=golden.corpus_version,
        source_matrix_id=presence_consensus.matrix_id,
        selection_sha256=detail_consensus.selection_sha256,
        published_cases=len(published),
        matched_cases=len(cases),
        missing_cases=tuple(missing),
        unresolved_count=unresolved,
        metrics=_metrics("hitl_v3_v4_consensus", predictions),
        cases=tuple(cases),
    )


def _load_candidate(
    directory: Path,
) -> tuple[ApplicabilityDetailSelection, ApplicabilityDetailEnrichmentReport]:
    selection_path = directory / APPLICABILITY_DETAIL_SELECTION_FILENAME
    report_path = directory / APPLICABILITY_DETAIL_REPORT_FILENAME
    if not selection_path.is_file():
        raise ValueError(
            f"candidate directory is missing {APPLICABILITY_DETAIL_SELECTION_FILENAME}"
        )
    if not report_path.is_file():
        raise ValueError(f"candidate directory is missing {APPLICABILITY_DETAIL_REPORT_FILENAME}")
    return load_applicability_detail_selection(selection_path), load_applicability_detail_report(
        report_path
    )


def _validate_pair(
    left_selection: ApplicabilityDetailSelection,
    left_report: ApplicabilityDetailEnrichmentReport,
    right_selection: ApplicabilityDetailSelection,
    right_report: ApplicabilityDetailEnrichmentReport,
) -> None:
    if left_selection.fingerprint != right_selection.fingerprint:
        raise ValueError("detail disagreement arms must reuse the exact same persisted selection")
    for label, selection, report in (
        ("left", left_selection, left_report),
        ("right", right_selection, right_report),
    ):
        if report.selection_sha256 != selection.fingerprint:
            raise ValueError(f"{label} detail report does not belong to its persisted selection")
        if report.processed_clause_count != report.selected_clause_count:
            raise ValueError(f"{label} detail report is incomplete")
        if report.selected_clause_count != selection.selected_clause_count:
            raise ValueError(f"{label} detail report selection count differs from selection")
        _validate_dual_decision_contract(report, label)
    if set(_by_coordinate(left_report, "left")) != set(_by_coordinate(right_report, "right")):
        raise ValueError("detail disagreement arms do not cover the same clause coordinates")


def _validate_dual_decision_contract(
    report: ApplicabilityDetailEnrichmentReport,
    label: str,
) -> None:
    for item in report.clauses:
        if item.outcome is ApplicabilityDetailOutcome.FAILED:
            continue
        if item.contains_clause_or_requirement_applicability is None:
            raise ValueError(
                f"{label} detail arm is not a dual-decision contract: "
                f"{item.document_key}/{item.clause_id}"
            )


def _detail_decision(item: ApplicabilityDetailClauseResult) -> bool | None:
    if item.outcome is ApplicabilityDetailOutcome.FAILED:
        return None
    if item.contains_clause_or_requirement_applicability is not None:
        return item.contains_clause_or_requirement_applicability
    return item.applicability_target is ApplicabilityTarget.CLAUSE_OR_REQUIREMENT


def _disagreement_kind(
    left: ApplicabilityDetailClauseResult,
    right: ApplicabilityDetailClauseResult,
) -> ApplicabilityDetailDisagreementKind | None:
    left_failed = left.outcome is ApplicabilityDetailOutcome.FAILED
    right_failed = right.outcome is ApplicabilityDetailOutcome.FAILED
    if left_failed and right_failed:
        return ApplicabilityDetailDisagreementKind.BOTH_FAILED
    if left_failed:
        return ApplicabilityDetailDisagreementKind.LEFT_FAILED
    if right_failed:
        return ApplicabilityDetailDisagreementKind.RIGHT_FAILED
    if _detail_decision(left) != _detail_decision(right):
        return ApplicabilityDetailDisagreementKind.DECISION
    return None


def _by_coordinate(
    report: ApplicabilityDetailEnrichmentReport,
    label: str,
) -> dict[tuple[str, str], ApplicabilityDetailClauseResult]:
    result = {(item.document_key, item.clause_id): item for item in report.clauses}
    if len(result) != len(report.clauses):
        raise ValueError(f"{label} detail coordinates must be unique")
    return result


def _load_dataset_text(run_archive: Path) -> dict[tuple[str, str], str]:
    with ZipFile(run_archive) as archive:
        member = _find_member(archive, "dataset.json")
        if member is None:
            raise ValueError("qualification archive does not contain inputs/corpus/dataset.json")
        payload = json.loads(archive.read(member))
    result: dict[tuple[str, str], str] = {}
    for example in payload.get("examples", ()):
        raw_input = example.get("input") or {}
        context = raw_input.get("context") or {}
        content = raw_input.get("content") or {}
        document_key = str(context.get("document_key") or "")
        clause_id = str(context.get("clause_id") or example.get("id") or "")
        if not document_key or not clause_id:
            continue
        text = str(content.get("text") or "") if isinstance(content, dict) else str(content)
        result[(document_key, clause_id)] = text
    return result


def _published_golden_by_coordinate(
    golden: ApplicabilityGoldenCorpus,
) -> dict[tuple[str, str], ApplicabilityGoldenCase]:
    return {
        (case.document_key, case.clause_id): case
        for case in golden.cases
        if case.status == "published" and case.expected is not None
    }


def _validate_golden_resolution(
    case: ApplicabilityGoldenCase,
    *,
    selected: Any,
    source_text: str,
) -> None:
    if case.reference != (selected.reference or ""):
        raise ValueError(
            "published Golden reference differs from the persisted detail selection for "
            f"{case.document_key}/{case.clause_id}"
        )
    golden_hash = "sha256:" + hashlib.sha256(case.text.encode("utf-8")).hexdigest()
    if golden_hash != selected.content_hash or case.text != source_text:
        raise ValueError(
            "published Golden text differs from the immutable qualification archive for "
            f"{case.document_key}/{case.clause_id}"
        )


def _review_has_human_edits(rows: list[dict[str, str]]) -> bool:
    for row in rows:
        status = (row.get("review_status") or "pending").strip().lower()
        decision = (row.get("contains_clause_or_requirement_applicability") or "").strip()
        note = (row.get("review_note") or "").strip()
        if status != "pending" or decision or note:
            return True
    return False


def _write_or_preserve_review(review_path: Path, rows: list[dict[str, str]]) -> bool:
    expected_coordinates = {(row["document_key"], row["clause_id"]) for row in rows}
    if review_path.exists():
        with review_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            existing_fields = tuple(reader.fieldnames or ())
            existing_rows = list(reader)
        existing_coordinates = {
            (
                (row.get("document_key") or "").strip(),
                (row.get("clause_id") or "").strip(),
            )
            for row in existing_rows
        }
        if _review_has_human_edits(existing_rows):
            if existing_coordinates != expected_coordinates:
                raise ValueError(
                    "existing HITL review contains human edits but belongs to a different "
                    "disagreement set; use a new --review-output"
                )
            return False
        if existing_coordinates == expected_coordinates and existing_fields == _REVIEW_FIELDS:
            return False

    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return True


def _review_row(
    *,
    selected: Any,
    text: str,
    selection_sha256: str,
    source_archive: str,
    source_archive_sha256: str,
    kind: ApplicabilityDetailDisagreementKind,
    left: ApplicabilityDetailClauseResult,
    right: ApplicabilityDetailClauseResult,
    left_report: ApplicabilityDetailEnrichmentReport,
    right_report: ApplicabilityDetailEnrichmentReport,
    left_report_sha256: str,
    right_report_sha256: str,
) -> dict[str, str]:
    return {
        "document_key": selected.document_key,
        "reference": selected.reference or "",
        "heading": selected.heading or "",
        "clause_id": selected.clause_id,
        "content_hash": selected.content_hash,
        "presence_confidence": str(selected.presence_confidence),
        "selection_sha256": selection_sha256,
        "source_archive": source_archive,
        "source_archive_sha256": source_archive_sha256,
        "disagreement_kind": kind.value,
        "left_model_id": left_report.model_id,
        "left_prompt_version": left_report.prompt_version,
        "left_report_sha256": left_report_sha256,
        "left_decision": _format_bool(_detail_decision(left)),
        "left_outcome": left.outcome.value,
        "left_other_targets": ";".join(item.value for item in left.other_applicability_targets),
        "left_functions": ";".join(item.value for item in left.applicability_functions),
        "left_evidence": _format_evidence(left),
        "right_model_id": right_report.model_id,
        "right_prompt_version": right_report.prompt_version,
        "right_report_sha256": right_report_sha256,
        "right_decision": _format_bool(_detail_decision(right)),
        "right_outcome": right.outcome.value,
        "right_other_targets": ";".join(item.value for item in right.other_applicability_targets),
        "right_functions": ";".join(item.value for item in right.applicability_functions),
        "right_evidence": _format_evidence(right),
        "text": text,
        "review_status": "pending",
        "contains_clause_or_requirement_applicability": "",
        "review_note": "",
    }


def _format_evidence(item: ApplicabilityDetailClauseResult) -> str:
    return " || ".join(f"{evidence.function.value}: {evidence.text}" for evidence in item.evidence)


def _write_review_guide(
    path: Path,
    *,
    left_report: ApplicabilityDetailEnrichmentReport,
    right_report: ApplicabilityDetailEnrichmentReport,
    golden: ApplicabilityGoldenCorpus,
    selected_clause_count: int,
    agreement_count: int,
    disagreement_count: int,
    golden_auto_resolved_count: int,
    new_hitl_count: int,
    source_failure_count: int,
) -> None:
    path.write_text(
        "# Applicability Detail Disagreement Review\n\n"
        "This review contains only new semantic primary-gate disagreements that are not already "
        "resolved by the published Applicability Golden corpus. Technical source failures are "
        "not sent to HITL and remain explicitly unresolved until the failed arm is rerun.\n\n"
        f"- left: `{left_report.model_id}` / `{left_report.prompt_version}`\n"
        f"- right: `{right_report.model_id}` / `{right_report.prompt_version}`\n"
        f"- Golden: `{golden.corpus_id}` / `{golden.corpus_version}`\n"
        f"- exact selection: {selected_clause_count}\n"
        f"- automatic agreements: {agreement_count}\n"
        f"- semantic disagreements: {disagreement_count}\n"
        f"- Golden auto-resolved: {golden_auto_resolved_count}\n"
        f"- new HITL cases: {new_hitl_count}\n"
        f"- technical source failures: {source_failure_count}\n\n"
        "For every CSV row answer exactly this question:\n\n"
        "> Does the clause text contain at least one explicit statement that determines "
        "whether a normative clause, requirement, recommendation, or provision applies, "
        "does not apply, is in scope, is excluded/waived, or becomes applicable under a "
        "stated condition?\n\n"
        "Do not infer clause applicability merely because a method, technique, activity, "
        "object, threshold, engineering status, or execution step is conditional. Other "
        "applicability targets are diagnostic context and are not evidence by themselves.\n\n"
        "The three editable review columns are intentionally placed directly after document_key, "
        "reference, and heading. Set `contains_clause_or_requirement_applicability=true` or "
        "`false`, then set `review_status=published`. Use `review_note` for the rationale. "
        "Leave all source/provenance columns unchanged. Rows left as `pending` remain unresolved "
        "in the published consensus.\n",
        encoding="utf-8",
    )


def _load_review_rows(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = set(_REVIEW_FIELDS) - fields
        if missing:
            raise ValueError(
                "HITL disagreement review is missing required columns: "
                + ", ".join(sorted(missing))
            )
        rows = list(reader)
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        coordinate = (
            (row.get("document_key") or "").strip(),
            (row.get("clause_id") or "").strip(),
        )
        if not all(coordinate):
            raise ValueError("HITL disagreement review contains an empty coordinate")
        if coordinate in result:
            raise ValueError(f"duplicate HITL disagreement review coordinate: {coordinate}")
        result[coordinate] = row
    return result


def _validate_review_row(
    row: dict[str, str],
    *,
    selected: Any,
    selection_sha256: str,
    source_archive: str,
    source_archive_sha256: str,
    source_text: str,
    kind: ApplicabilityDetailDisagreementKind,
    left: ApplicabilityDetailClauseResult,
    right: ApplicabilityDetailClauseResult,
    left_report: ApplicabilityDetailEnrichmentReport,
    right_report: ApplicabilityDetailEnrichmentReport,
    left_report_sha256: str,
    right_report_sha256: str,
) -> None:
    expected = {
        "document_key": selected.document_key,
        "clause_id": selected.clause_id,
        "content_hash": selected.content_hash,
        "selection_sha256": selection_sha256,
        "source_archive": source_archive,
        "source_archive_sha256": source_archive_sha256,
        "disagreement_kind": kind.value,
        "left_model_id": left_report.model_id,
        "left_prompt_version": left_report.prompt_version,
        "left_report_sha256": left_report_sha256,
        "left_decision": _format_bool(_detail_decision(left)),
        "left_outcome": left.outcome.value,
        "right_model_id": right_report.model_id,
        "right_prompt_version": right_report.prompt_version,
        "right_report_sha256": right_report_sha256,
        "right_decision": _format_bool(_detail_decision(right)),
        "right_outcome": right.outcome.value,
        "text": source_text,
    }
    for field, value in expected.items():
        if (row.get(field) or "").strip() != value:
            raise ValueError(
                "HITL disagreement review source/provenance changed for "
                f"{selected.document_key}/{selected.clause_id}: {field}"
            )


def _parse_bool_required(value: str | None, *, coordinate: tuple[str, str]) -> bool:
    normalized = (value or "").strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(
        f"published HITL rows require true/false decision for {coordinate[0]}/{coordinate[1]}"
    )


def _format_bool(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
