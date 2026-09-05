"""Offline end-to-end evaluation for applicability Presence plus detail verification."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal
from zipfile import ZipFile

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.applicability_corpus import (
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
)
from standards_atlas.application.semantic_qualification.applicability_hard_cases import _find_member
from standards_atlas.application.semantic_qualification.consensus import ConsensusReport
from standards_atlas.domain.model import ApplicabilityTarget

_FINAL_DETAIL_CONSENSUS_MEMBER = "inputs/applicability-detail/final-consensus-report.json"


class ApplicabilityDetailVerificationMetrics(BaseModel):
    """Verification quality and operational accounting for Presence-positive candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metrics: ApplicabilityModelMetrics
    source_presence_candidate_count: int = Field(ge=0)
    golden_presence_candidate_count: int = Field(ge=0)
    evaluated_candidate_count: int = Field(ge=0)
    confirmed_clause_applicability_count: int = Field(ge=0)
    rejected_non_clause_count: int = Field(ge=0)
    failed_candidate_count: int = Field(ge=0)
    true_positive_candidate_count: int = Field(ge=0)
    false_positive_candidate_count: int = Field(ge=0)
    true_positive_retained_count: int = Field(ge=0)
    true_positive_rejected_count: int = Field(ge=0)
    false_positive_rejected_count: int = Field(ge=0)
    false_positive_retained_count: int = Field(ge=0)
    failed_true_positive_count: int = Field(ge=0)
    failed_false_positive_count: int = Field(ge=0)
    outcome_counts: dict[str, int] = Field(default_factory=dict)
    target_counts: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_accounting(self) -> ApplicabilityDetailVerificationMetrics:
        if (
            self.evaluated_candidate_count + self.failed_candidate_count
            != self.golden_presence_candidate_count
        ):
            raise ValueError("detail verification candidate accounting does not balance")
        if (
            self.confirmed_clause_applicability_count + self.rejected_non_clause_count
            != self.evaluated_candidate_count
        ):
            raise ValueError("detail verification decision accounting does not balance")
        if (
            self.true_positive_candidate_count + self.false_positive_candidate_count
            != self.golden_presence_candidate_count
        ):
            raise ValueError("detail verification golden candidate accounting does not balance")
        if (
            self.true_positive_retained_count
            + self.true_positive_rejected_count
            + self.failed_true_positive_count
            != self.true_positive_candidate_count
        ):
            raise ValueError("detail verification positive accounting does not balance")
        if (
            self.false_positive_rejected_count
            + self.false_positive_retained_count
            + self.failed_false_positive_count
            != self.false_positive_candidate_count
        ):
            raise ValueError("detail verification negative accounting does not balance")
        return self


class ApplicabilityEndToEndCase(BaseModel):
    """Traceable final decision for one published golden case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str
    clause_id: str
    reference: str
    expected_present: bool
    presence_present: bool
    detail_outcome: ApplicabilityDetailOutcome | None = None
    applicability_target: ApplicabilityTarget | None = None
    final_present: bool | None = None
    final_error: Literal["false_positive", "false_negative"] | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> ApplicabilityEndToEndCase:
        if not self.presence_present:
            if self.detail_outcome is not None or self.applicability_target is not None:
                raise ValueError("Presence-negative cases must not contain detail verification")
            if self.final_present is not False:
                raise ValueError("Presence-negative cases resolve end-to-end as false")
        elif self.detail_outcome is ApplicabilityDetailOutcome.FAILED:
            if self.final_present is not None:
                raise ValueError("failed detail verification leaves end-to-end unresolved")
        elif self.detail_outcome is ApplicabilityDetailOutcome.NOT_CONFIRMED:
            if self.final_present is not False:
                raise ValueError("not_confirmed detail verification resolves false")
        elif self.detail_outcome in {
            ApplicabilityDetailOutcome.ENRICHED,
            ApplicabilityDetailOutcome.UNRESOLVED,
        }:
            if self.applicability_target is not ApplicabilityTarget.CLAUSE_OR_REQUIREMENT:
                raise ValueError(
                    "confirmed detail verification requires clause-or-requirement target"
                )
            if self.final_present is not True:
                raise ValueError("confirmed detail verification resolves true")
        elif self.presence_present:
            raise ValueError("Presence-positive cases require a detail verification outcome")

        expected_error = None
        if self.final_present is not None and self.final_present != self.expected_present:
            expected_error = "false_negative" if self.expected_present else "false_positive"
        if self.final_error != expected_error:
            raise ValueError("end-to-end final_error does not match the final decision")
        return self


class ApplicabilityEndToEndRegressionReport(BaseModel):
    """Offline evaluation of final Presence consensus plus sparse detail verification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    golden_corpus_id: str
    golden_corpus_version: str
    source_matrix_id: str
    published_cases: int = Field(ge=0)
    matched_cases: int = Field(ge=0)
    missing_cases: tuple[str, ...] = ()
    positive_cases: int = Field(ge=0)
    negative_cases: int = Field(ge=0)
    presence_detection: ApplicabilityModelMetrics
    detail_verification: ApplicabilityDetailVerificationMetrics
    end_to_end: ApplicabilityModelMetrics
    end_to_end_unresolved_count: int = Field(ge=0)
    end_to_end_unresolved_cases: tuple[str, ...] = ()
    cases: tuple[ApplicabilityEndToEndCase, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> ApplicabilityEndToEndRegressionReport:
        if self.positive_cases + self.negative_cases != self.published_cases:
            raise ValueError("end-to-end golden class balance does not match published cases")
        if self.matched_cases + len(self.missing_cases) != self.published_cases:
            raise ValueError("end-to-end matched/missing accounting does not balance")
        if len(self.cases) != self.matched_cases:
            raise ValueError("end-to-end case count must match matched cases")
        if self.presence_detection.evaluated_cases != self.matched_cases:
            raise ValueError("Presence evaluation must cover every matched golden case")
        if self.end_to_end.evaluated_cases + self.end_to_end_unresolved_count != self.matched_cases:
            raise ValueError("end-to-end resolved/unresolved accounting does not balance")
        if self.end_to_end_unresolved_count != len(self.end_to_end_unresolved_cases):
            raise ValueError("end-to-end unresolved case count does not match references")
        return self


def evaluate_applicability_end_to_end(
    golden: ApplicabilityGoldenCorpus,
    run_archive: Path,
) -> ApplicabilityEndToEndRegressionReport:
    """Evaluate archived final Presence decisions and detail verification without inference."""

    published = tuple(
        case for case in golden.cases if case.status == "published" and case.expected is not None
    )
    if not published:
        raise ValueError("applicability golden corpus contains no published cases")

    consensus, selection, detail = _load_end_to_end_artifacts(run_archive)
    _validate_detail_provenance(consensus=consensus, selection=selection, detail=detail)

    consensus_by_coordinate = {
        (item.document_key, item.clause_id): item for item in consensus.clauses
    }
    if len(consensus_by_coordinate) != len(consensus.clauses):
        raise ValueError("final applicability consensus coordinates must be unique")
    detail_by_coordinate = {(item.document_key, item.clause_id): item for item in detail.clauses}
    if len(detail_by_coordinate) != len(detail.clauses):
        raise ValueError("applicability detail result coordinates must be unique")

    matched = []
    missing: list[str] = []
    for case in published:
        coordinate = (case.document_key, case.clause_id)
        if coordinate not in consensus_by_coordinate:
            missing.append(f"{case.document_key}/{case.clause_id}")
            continue
        matched.append(case)

    presence_predictions: list[tuple[bool, ApplicabilityGoldenExpected]] = []
    detail_predictions: list[tuple[bool, ApplicabilityGoldenExpected]] = []
    final_predictions: list[tuple[bool, ApplicabilityGoldenExpected]] = []
    cases: list[ApplicabilityEndToEndCase] = []
    unresolved_cases: list[str] = []
    outcome_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()

    true_positive_candidates = 0
    false_positive_candidates = 0
    true_positive_retained = 0
    true_positive_rejected = 0
    false_positive_rejected = 0
    false_positive_retained = 0
    failed_true_positive = 0
    failed_false_positive = 0
    confirmed = 0
    rejected = 0
    failed = 0

    for case in matched:
        expected = case.expected
        assert expected is not None
        coordinate = (case.document_key, case.clause_id)
        consensus_clause = consensus_by_coordinate[coordinate]
        presence_present = consensus_clause.applicability_present
        presence_predictions.append((presence_present, expected))

        detail_result: ApplicabilityDetailClauseResult | None = None
        final_present: bool | None
        if not presence_present:
            final_present = False
            final_predictions.append((False, expected))
        else:
            detail_result = detail_by_coordinate.get(coordinate)
            if detail_result is None:
                raise ValueError(
                    "Presence-positive golden case is missing applicability detail verification: "
                    f"{case.document_key}/{case.clause_id}"
                )
            outcome_counts[detail_result.outcome.value] += 1
            if detail_result.applicability_target is not None:
                target_counts[detail_result.applicability_target.value] += 1

            if expected.present:
                true_positive_candidates += 1
            else:
                false_positive_candidates += 1

            if detail_result.outcome is ApplicabilityDetailOutcome.FAILED:
                failed += 1
                final_present = None
                unresolved_cases.append(f"{case.document_key}/{case.clause_id}")
                if expected.present:
                    failed_true_positive += 1
                else:
                    failed_false_positive += 1
            elif detail_result.outcome is ApplicabilityDetailOutcome.NOT_CONFIRMED:
                rejected += 1
                final_present = False
                detail_predictions.append((False, expected))
                final_predictions.append((False, expected))
                if expected.present:
                    true_positive_rejected += 1
                else:
                    false_positive_rejected += 1
            else:
                if (
                    detail_result.applicability_target
                    is not ApplicabilityTarget.CLAUSE_OR_REQUIREMENT
                ):
                    raise ValueError(
                        "confirmed applicability detail result has a non-clause target: "
                        f"{case.document_key}/{case.clause_id}"
                    )
                confirmed += 1
                final_present = True
                detail_predictions.append((True, expected))
                final_predictions.append((True, expected))
                if expected.present:
                    true_positive_retained += 1
                else:
                    false_positive_retained += 1

        final_error = None
        if final_present is not None and final_present != expected.present:
            final_error = "false_negative" if expected.present else "false_positive"
        cases.append(
            ApplicabilityEndToEndCase(
                document_key=case.document_key,
                clause_id=case.clause_id,
                reference=case.reference,
                expected_present=expected.present,
                presence_present=presence_present,
                detail_outcome=detail_result.outcome if detail_result is not None else None,
                applicability_target=(
                    detail_result.applicability_target if detail_result is not None else None
                ),
                final_present=final_present,
                final_error=final_error,
            )
        )

    presence_metrics = _metrics("final_cascade", presence_predictions)
    detail_metrics = _metrics("detail_verification", detail_predictions)
    end_to_end_metrics = _metrics("end_to_end", final_predictions)
    presence_candidate_count = presence_metrics.predicted_positive_cases

    detail_verification = ApplicabilityDetailVerificationMetrics(
        metrics=detail_metrics,
        source_presence_candidate_count=selection.selected_clause_count,
        golden_presence_candidate_count=presence_candidate_count,
        evaluated_candidate_count=confirmed + rejected,
        confirmed_clause_applicability_count=confirmed,
        rejected_non_clause_count=rejected,
        failed_candidate_count=failed,
        true_positive_candidate_count=true_positive_candidates,
        false_positive_candidate_count=false_positive_candidates,
        true_positive_retained_count=true_positive_retained,
        true_positive_rejected_count=true_positive_rejected,
        false_positive_rejected_count=false_positive_rejected,
        false_positive_retained_count=false_positive_retained,
        failed_true_positive_count=failed_true_positive,
        failed_false_positive_count=failed_false_positive,
        outcome_counts=dict(sorted(outcome_counts.items())),
        target_counts=dict(sorted(target_counts.items())),
    )

    positive_cases = sum(bool(case.expected and case.expected.present) for case in published)
    return ApplicabilityEndToEndRegressionReport(
        golden_corpus_id=golden.corpus_id,
        golden_corpus_version=golden.corpus_version,
        source_matrix_id=consensus.matrix_id,
        published_cases=len(published),
        matched_cases=len(matched),
        missing_cases=tuple(missing),
        positive_cases=positive_cases,
        negative_cases=len(published) - positive_cases,
        presence_detection=presence_metrics,
        detail_verification=detail_verification,
        end_to_end=end_to_end_metrics,
        end_to_end_unresolved_count=len(unresolved_cases),
        end_to_end_unresolved_cases=tuple(unresolved_cases),
        cases=tuple(cases),
    )


def _load_end_to_end_artifacts(
    run_archive: Path,
) -> tuple[ConsensusReport, ApplicabilityDetailSelection, ApplicabilityDetailEnrichmentReport]:
    with ZipFile(run_archive) as archive:
        consensus_member = (
            _FINAL_DETAIL_CONSENSUS_MEMBER
            if _FINAL_DETAIL_CONSENSUS_MEMBER in archive.namelist()
            else _find_member(archive, "consensus-report.json")
        )
        if consensus_member is None:
            raise ValueError("qualification run does not contain final consensus-report.json")
        selection_member = _find_member(archive, APPLICABILITY_DETAIL_SELECTION_FILENAME)
        detail_member = _find_member(archive, APPLICABILITY_DETAIL_REPORT_FILENAME)
        if selection_member is None or detail_member is None:
            raise ValueError(
                "qualification run does not contain completed applicability detail artifacts; "
                "run applicability-detail-enrich --fresh and archive the qualification run"
            )
        consensus = ConsensusReport.model_validate_json(archive.read(consensus_member))
        selection = ApplicabilityDetailSelection.model_validate_json(archive.read(selection_member))
        try:
            detail = ApplicabilityDetailEnrichmentReport.model_validate_json(
                archive.read(detail_member)
            )
        except ValueError as exc:
            raise ValueError(
                "qualification run contains an applicability detail report incompatible with "
                "target verification; rerun applicability-detail-enrich --fresh and archive "
                "the qualification run"
            ) from exc
    return consensus, selection, detail


def _validate_detail_provenance(
    *,
    consensus: ConsensusReport,
    selection: ApplicabilityDetailSelection,
    detail: ApplicabilityDetailEnrichmentReport,
) -> None:
    if consensus.matrix_id != selection.source_matrix_id:
        raise ValueError("applicability detail selection belongs to a different consensus matrix")
    if consensus.corpus_id != selection.source_corpus_id:
        raise ValueError("applicability detail selection belongs to a different consensus corpus")
    if selection.source_consensus_clause_count != len(consensus.clauses):
        raise ValueError("applicability detail selection consensus count differs from consensus")
    consensus_sha256 = _canonical_sha256(consensus.model_dump(mode="json"))
    if selection.source_consensus_sha256 != consensus_sha256:
        raise ValueError("applicability detail selection belongs to a different final consensus")
    if detail.selection_sha256 != selection.fingerprint:
        raise ValueError("applicability detail report belongs to a different detail selection")
    if detail.selected_clause_count != selection.selected_clause_count:
        raise ValueError("applicability detail report selection count differs from selection")
    if detail.processed_clause_count != detail.selected_clause_count:
        raise ValueError("applicability detail report is incomplete")

    expected_positive_coordinates = {
        (item.document_key, item.clause_id)
        for item in consensus.clauses
        if item.applicability_present
    }
    selection_coordinates = {(item.document_key, item.clause_id) for item in selection.clauses}
    detail_coordinates = {(item.document_key, item.clause_id) for item in detail.clauses}
    if selection_coordinates != expected_positive_coordinates:
        raise ValueError(
            "applicability detail selection does not match final Presence-positive consensus"
        )
    if detail_coordinates != selection_coordinates:
        raise ValueError("applicability detail report does not cover the complete detail selection")


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
