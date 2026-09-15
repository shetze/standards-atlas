"""Qualification metrics for applicability-presence proposal runs."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.application.semantic_qualification.annotations import (
    AnnotationLifecycleStatus,
    AnnotationResolutionSource,
    ApplicabilityPresenceSelection,
    ClauseAnnotationResolver,
    ClauseEvaluationAnnotation,
    CorpusManifestRepository,
)
from standards_atlas.application.semantic_qualification.reports.applicability import (
    render_applicability_qualification_markdown,
)


class ApplicabilityAgreementMetrics(BaseModel):
    """Binary agreement against reviewed applicability-presence evidence."""

    model_config = ConfigDict(frozen=True)

    eligible: int = Field(ge=0)
    evaluated: int = Field(ge=0)
    coverage: float = Field(ge=0.0, le=1.0)
    accuracy: float = Field(ge=0.0, le=1.0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    specificity: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    true_negative: int = Field(ge=0)
    false_negative: int = Field(ge=0)


class CalibrationBin(BaseModel):
    model_config = ConfigDict(frozen=True)

    lower: float
    upper: float
    count: int = Field(ge=0)
    mean_confidence: float | None = None
    accuracy: float | None = None


class CalibrationMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    covered: int = Field(ge=0)
    coverage: float = Field(ge=0.0, le=1.0)
    brier_score: float | None = None
    expected_calibration_error: float | None = None
    bins: tuple[CalibrationBin, ...] = ()


class EvaluationSliceReport(BaseModel):
    """Gold-set applicability performance for one corpus stratum."""

    model_config = ConfigDict(frozen=True)

    dimension: str
    value: str
    cases: int = Field(ge=0)
    gold: ApplicabilityAgreementMetrics


class CorpusCoverage(BaseModel):
    model_config = ConfigDict(frozen=True)

    corpus_clauses: int = Field(ge=0)
    predictions: int = Field(ge=0)
    published_gold: int = Field(ge=0)
    local_reviewed_gold: int = Field(ge=0)
    local_proposals: int = Field(ge=0)
    stale_or_invalid: int = Field(ge=0)
    missing_predictions: int = Field(ge=0)


class FailureCategoryCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    count: int = Field(ge=1)


class FailureMessageCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str
    count: int = Field(ge=1)


class ReliabilityMetrics(BaseModel):
    """Operational reliability of one proposal run."""

    model_config = ConfigDict(frozen=True)

    attempted_clauses: int = Field(ge=0)
    successful_predictions: int = Field(ge=0)
    failed_responses: int = Field(ge=0)
    truncated_responses: int = Field(ge=0)
    invalid_json_responses: int = Field(ge=0)
    timeout_responses: int = Field(ge=0)
    prediction_success_rate: float = Field(ge=0.0, le=1.0)
    json_validity_rate: float = Field(ge=0.0, le=1.0)
    truncation_rate: float = Field(ge=0.0, le=1.0)
    failure_categories: tuple[FailureCategoryCount, ...] = ()
    top_failure_messages: tuple[FailureMessageCount, ...] = ()


_DEFAULT_RELIABILITY = ReliabilityMetrics(
    attempted_clauses=0,
    successful_predictions=0,
    failed_responses=0,
    truncated_responses=0,
    invalid_json_responses=0,
    timeout_responses=0,
    prediction_success_rate=0.0,
    json_validity_rate=0.0,
    truncation_rate=0.0,
)


class ApplicabilityQualificationReport(SchemaBoundModel):
    """Machine-readable qualification result for applicability presence."""

    SCHEMA_FAMILY: ClassVar[str] = "applicability-qualification-report"

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    corpus_id: str
    generated_at: datetime
    prediction_source: str
    coverage: CorpusCoverage
    reliability: ReliabilityMetrics = _DEFAULT_RELIABILITY
    gold_agreement: ApplicabilityAgreementMetrics
    calibration: CalibrationMetrics
    slices: tuple[EvaluationSliceReport, ...] = ()
    diagnostics: tuple[str, ...] = ()


class ApplicabilityQualificationService:
    """Evaluate one applicability-presence proposal run against reviewed evidence."""

    def evaluate(
        self,
        *,
        corpus_id: str,
        run_directory: Path,
        local_corpus_root: Path,
        published_corpus_root: Path,
        output_directory: Path,
        example_ids: tuple[str, ...] | None = None,
    ) -> tuple[ApplicabilityQualificationReport, Path, Path]:
        manifest = CorpusManifestRepository(local_corpus_root).load(corpus_id)
        resolver = ClauseAnnotationResolver(
            local_root=local_corpus_root,
            published_root=published_corpus_root,
        )
        predictions = _load_predictions(run_directory)
        rows: list[_Row] = []
        diagnostics: list[str] = []
        source_counts: Counter[str] = Counter()
        invalid = 0
        included_example_ids = set(example_ids or ())

        for member in manifest.clauses:
            if included_example_ids and member.clause.clause_id not in included_example_ids:
                continue
            key = member.clause.key
            resolved = None
            try:
                resolved = resolver.resolve(corpus_id, member.clause)
            except (OSError, ValueError, RuntimeError) as exc:
                invalid += 1
                diagnostics.append(f"{key}: {type(exc).__name__}: {exc}")
            if resolved is not None:
                source_counts[resolved.source.value] += 1
            rows.append(
                _Row(
                    key=key,
                    prediction=predictions.get(key),
                    resolved=resolved.annotation if resolved else None,
                    strata=member.strata,
                )
            )

        gold_pairs = _gold_pairs(rows)
        gold_eligible = sum(_gold_selection(row) is not None for row in rows)
        reliability = _reliability(
            run_directory,
            attempted=len(rows),
            successful=sum(row.prediction is not None for row in rows),
        )
        report = ApplicabilityQualificationReport(
            corpus_id=corpus_id,
            generated_at=datetime.now(UTC),
            prediction_source=str(run_directory),
            coverage=CorpusCoverage(
                corpus_clauses=len(rows),
                predictions=sum(row.prediction is not None for row in rows),
                published_gold=source_counts[AnnotationResolutionSource.PUBLISHED.value],
                local_reviewed_gold=source_counts[AnnotationResolutionSource.LOCAL_REVIEWED.value],
                local_proposals=source_counts[AnnotationResolutionSource.LOCAL_PROPOSAL.value],
                stale_or_invalid=invalid,
                missing_predictions=sum(row.prediction is None for row in rows),
            ),
            reliability=reliability,
            gold_agreement=_agreement(gold_pairs, eligible=gold_eligible),
            calibration=_calibration(gold_pairs),
            slices=_slice_reports(rows),
            diagnostics=tuple(diagnostics),
        )
        output_directory.mkdir(parents=True, exist_ok=True)
        json_path = output_directory / "applicability-qualification.json"
        md_path = output_directory / "applicability-qualification.md"
        json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        md_path.write_text(render_applicability_qualification_markdown(report), encoding="utf-8")
        return report, json_path, md_path


class _Row(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    key: str
    prediction: ApplicabilityPresenceSelection | None
    resolved: ClauseEvaluationAnnotation | None
    strata: dict[str, str]


def _gold_selection(row: _Row) -> ApplicabilityPresenceSelection | None:
    if row.resolved is None:
        return None
    if row.resolved.lifecycle_status not in {
        AnnotationLifecycleStatus.REVIEWED,
        AnnotationLifecycleStatus.PUBLISHED,
    }:
        return None
    return row.resolved.annotation


def _gold_pairs(
    rows: list[_Row],
) -> list[tuple[ApplicabilityPresenceSelection, ApplicabilityPresenceSelection]]:
    pairs = []
    for row in rows:
        expected = _gold_selection(row)
        if row.prediction is not None and expected is not None:
            pairs.append((row.prediction, expected))
    return pairs


def _agreement(
    pairs: list[tuple[ApplicabilityPresenceSelection, ApplicabilityPresenceSelection]],
    *,
    eligible: int,
) -> ApplicabilityAgreementMetrics:
    tp = fp = tn = fn = 0
    for predicted, expected in pairs:
        p = predicted.applicability_present
        e = expected.applicability_present
        if p and e:
            tp += 1
        elif p and not e:
            fp += 1
        elif not p and not e:
            tn += 1
        else:
            fn += 1
    count = len(pairs)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    specificity = tn / (tn + fp) if tn + fp else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return ApplicabilityAgreementMetrics(
        eligible=eligible,
        evaluated=count,
        coverage=count / eligible if eligible else 0.0,
        accuracy=(tp + tn) / count if count else 0.0,
        precision=precision if count else 0.0,
        recall=recall if count else 0.0,
        specificity=specificity if count else 0.0,
        f1=f1 if count else 0.0,
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
    )


def _calibration(
    pairs: list[tuple[ApplicabilityPresenceSelection, ApplicabilityPresenceSelection]],
) -> CalibrationMetrics:
    entries = [
        (
            predicted.confidence,
            int(predicted.applicability_present == expected.applicability_present),
        )
        for predicted, expected in pairs
        if predicted.confidence is not None
    ]
    bins: list[CalibrationBin] = []
    weighted_error = 0.0
    for index in range(10):
        lower, upper = index / 10, (index + 1) / 10
        bucket = [
            (confidence, correct)
            for confidence, correct in entries
            if lower <= confidence <= upper and (index == 9 or confidence < upper)
        ]
        if bucket:
            mean = sum(confidence for confidence, _ in bucket) / len(bucket)
            accuracy = sum(correct for _, correct in bucket) / len(bucket)
            weighted_error += len(bucket) * abs(mean - accuracy)
            bins.append(
                CalibrationBin(
                    lower=lower,
                    upper=upper,
                    count=len(bucket),
                    mean_confidence=mean,
                    accuracy=accuracy,
                )
            )
        else:
            bins.append(CalibrationBin(lower=lower, upper=upper, count=0))
    return CalibrationMetrics(
        covered=len(entries),
        coverage=len(entries) / len(pairs) if pairs else 0.0,
        brier_score=(
            sum((confidence - correct) ** 2 for confidence, correct in entries) / len(entries)
            if entries
            else None
        ),
        expected_calibration_error=(weighted_error / len(entries) if entries else None),
        bins=tuple(bins),
    )


def _slice_reports(rows: list[_Row]) -> tuple[EvaluationSliceReport, ...]:
    grouped: dict[tuple[str, str], list[_Row]] = defaultdict(list)
    for row in rows:
        domain = row.key.split(":", 1)[0]
        grouped[("knowledge_domain", domain)].append(row)
        for dimension, value in row.strata.items():
            grouped[(dimension, value)].append(row)

    reports = []
    for (dimension, value), group in sorted(grouped.items()):
        pairs = _gold_pairs(group)
        eligible = sum(_gold_selection(row) is not None for row in group)
        reports.append(
            EvaluationSliceReport(
                dimension=dimension,
                value=value,
                cases=len(group),
                gold=_agreement(pairs, eligible=eligible),
            )
        )
    return tuple(reports)


def _load_predictions(run_directory: Path) -> dict[str, ApplicabilityPresenceSelection]:
    predictions: dict[str, ApplicabilityPresenceSelection] = {}
    for path in sorted(run_directory.rglob("evaluation.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        candidate = ClauseEvaluationAnnotation.model_validate(payload["annotation_candidate"])
        key = candidate.clause.key
        if key in predictions:
            raise ValueError(f"duplicate prediction for {key}: {path}")
        predictions[key] = candidate.proposal
    return predictions


def _reliability(run_directory: Path, *, attempted: int, successful: int) -> ReliabilityMetrics:
    categories: Counter[str] = Counter()
    messages: Counter[str] = Counter()
    truncated = invalid_json = timeouts = failures = 0
    for path in run_directory.rglob("failure.json"):
        failures += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            categories["unreadable_failure_record"] += 1
            messages[f"{type(exc).__name__}: {exc}"] += 1
            continue
        error = payload.get("error", {})
        raw_category = str(error.get("category", "")).strip()
        message = str(error.get("message", "")).strip()
        category = _failure_category(raw_category, message)
        categories[category] += 1
        if message:
            messages[message[:500]] += 1
        if category == "truncated_response":
            truncated += 1
        if category in {"invalid_json", "truncated_response"}:
            invalid_json += 1
        if category == "timeout":
            timeouts += 1
    denominator = attempted or 1
    json_denominator = max(successful + invalid_json, 1)
    return ReliabilityMetrics(
        attempted_clauses=attempted,
        successful_predictions=successful,
        failed_responses=failures,
        truncated_responses=truncated,
        invalid_json_responses=invalid_json,
        timeout_responses=timeouts,
        prediction_success_rate=successful / denominator,
        json_validity_rate=successful / json_denominator,
        truncation_rate=truncated / denominator,
        failure_categories=tuple(
            FailureCategoryCount(category=category, count=count)
            for category, count in categories.most_common()
        ),
        top_failure_messages=tuple(
            FailureMessageCount(message=message, count=count)
            for message, count in messages.most_common(10)
        ),
    )


def _failure_category(raw_category: str, message: str) -> str:
    normalized = raw_category.lower().replace("-", "_").strip()
    lower_message = message.lower()
    if normalized == "truncated_response" or "finish_reason=length" in lower_message:
        return "truncated_response"
    if normalized == "timeout" or "timed out" in lower_message:
        return "timeout"
    if normalized in {"invalid_json", "json_decode_error"} or "not valid json" in lower_message:
        return "invalid_json"
    if normalized in {"schema_validation_error", "validation_error"} or (
        "validation" in lower_message and "json" not in lower_message
    ):
        return "schema_validation_error"
    if normalized in {"provider_error", "transport_error", "connection_error"}:
        return normalized
    return normalized or "other"
