"""Annotation resolution and qualification metrics for semantic-role corpora."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.services.evaluation.annotations import (
    AnnotationLifecycleStatus,
    AnnotationResolutionSource,
    ClauseAnnotationResolver,
    ClauseEvaluationAnnotation,
    CorpusManifestRepository,
    SemanticRoleSelection,
)
from standards_atlas.domain.model import SemanticRole


class AgreementMetrics(BaseModel):
    """Multi-label and primary-role agreement against one evidence source."""

    model_config = ConfigDict(frozen=True)

    eligible: int = Field(ge=0)
    evaluated: int = Field(ge=0)
    coverage: float = Field(ge=0.0, le=1.0)
    exact_match_rate: float = Field(ge=0.0, le=1.0)
    primary_role_accuracy: float = Field(ge=0.0, le=1.0)
    micro_precision: float = Field(ge=0.0, le=1.0)
    micro_recall: float = Field(ge=0.0, le=1.0)
    micro_f1: float = Field(ge=0.0, le=1.0)
    macro_f1: float = Field(ge=0.0, le=1.0)


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


class ConfusionEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected: str
    predicted: str
    count: int = Field(ge=1)


class EvaluationSliceReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    value: str
    cases: int = Field(ge=0)
    gold: AgreementMetrics
    silver: AgreementMetrics
    structure: AgreementMetrics


class CorpusCoverage(BaseModel):
    model_config = ConfigDict(frozen=True)

    corpus_clauses: int = Field(ge=0)
    predictions: int = Field(ge=0)
    published_gold: int = Field(ge=0)
    local_reviewed_gold: int = Field(ge=0)
    local_proposals: int = Field(ge=0)
    structure_labels: int = Field(ge=0)
    stale_or_invalid: int = Field(ge=0)
    missing_predictions: int = Field(ge=0)


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


class AnnotationQualificationReport(BaseModel):
    """Machine-readable result of Slice 5.4.5 qualification."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    corpus_id: str
    generated_at: datetime
    prediction_source: str
    coverage: CorpusCoverage
    reliability: ReliabilityMetrics = ReliabilityMetrics(
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
    gold_agreement: AgreementMetrics
    silver_agreement: AgreementMetrics
    structure_agreement: AgreementMetrics
    calibration: CalibrationMetrics
    primary_role_confusion: tuple[ConfusionEntry, ...] = ()
    slices: tuple[EvaluationSliceReport, ...] = ()
    diagnostics: tuple[str, ...] = ()


class AnnotationQualificationService:
    """Resolve evidence by priority and evaluate one proposal run on a corpus."""

    def evaluate(
        self,
        *,
        corpus_id: str,
        run_directory: Path,
        local_corpus_root: Path,
        published_corpus_root: Path,
        output_directory: Path,
    ) -> tuple[AnnotationQualificationReport, Path, Path]:
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

        for member in manifest.clauses:
            key = member.clause.key
            prediction = predictions.get(key)
            structure = _structure_selection(member.strata)
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
                    prediction=prediction,
                    resolved=resolved.annotation if resolved else None,
                    resolution_source=resolved.source if resolved else None,
                    structure=structure,
                    strata=member.strata,
                )
            )

        gold_pairs = [
            (row.prediction, row.resolved.annotation)
            for row in rows
            if row.prediction is not None
            and row.resolved is not None
            and row.resolved.lifecycle_status
            in {AnnotationLifecycleStatus.REVIEWED, AnnotationLifecycleStatus.PUBLISHED}
            and row.resolved.annotation is not None
        ]
        silver_pairs = []
        for row in rows:
            if row.prediction is None:
                continue
            expected = _silver_expected(row)
            if expected is not None:
                silver_pairs.append((row.prediction, expected))
        structure_pairs = [
            (row.prediction, row.structure)
            for row in rows
            if row.prediction is not None and row.structure is not None
        ]

        reliability = _reliability(run_directory, attempted=len(rows), successful=len(predictions))
        report = AnnotationQualificationReport(
            corpus_id=corpus_id,
            generated_at=datetime.now(UTC),
            prediction_source=str(run_directory),
            coverage=CorpusCoverage(
                corpus_clauses=len(rows),
                predictions=sum(row.prediction is not None for row in rows),
                published_gold=source_counts[AnnotationResolutionSource.PUBLISHED.value],
                local_reviewed_gold=source_counts[AnnotationResolutionSource.LOCAL_REVIEWED.value],
                local_proposals=source_counts[AnnotationResolutionSource.LOCAL_PROPOSAL.value],
                structure_labels=sum(row.structure is not None for row in rows),
                stale_or_invalid=invalid,
                missing_predictions=sum(row.prediction is None for row in rows),
            ),
            reliability=reliability,
            gold_agreement=_agreement(
                gold_pairs,
                eligible=sum(
                    row.resolved is not None
                    and row.resolved.lifecycle_status
                    in {AnnotationLifecycleStatus.REVIEWED, AnnotationLifecycleStatus.PUBLISHED}
                    and row.resolved.annotation is not None
                    for row in rows
                ),
            ),
            silver_agreement=_agreement(
                silver_pairs, eligible=sum(_silver_expected(row) is not None for row in rows)
            ),
            structure_agreement=_agreement(
                structure_pairs, eligible=sum(row.structure is not None for row in rows)
            ),
            calibration=_calibration(gold_pairs),
            primary_role_confusion=_confusion(gold_pairs),
            slices=_slice_reports(rows),
            diagnostics=tuple(diagnostics),
        )
        output_directory.mkdir(parents=True, exist_ok=True)
        json_path = output_directory / "qualification.json"
        md_path = output_directory / "qualification.md"
        json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        md_path.write_text(_markdown(report), encoding="utf-8")
        return report, json_path, md_path


class _Row(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    key: str
    prediction: SemanticRoleSelection | None
    resolved: ClauseEvaluationAnnotation | None
    resolution_source: AnnotationResolutionSource | None
    structure: SemanticRoleSelection | None
    strata: dict[str, str]


def _reliability(run_directory: Path, *, attempted: int, successful: int) -> ReliabilityMetrics:
    truncated = invalid_json = timeouts = failures = 0
    for path in run_directory.rglob("failure.json"):
        failures += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        error = payload.get("error", {})
        category = str(error.get("category", ""))
        message = str(error.get("message", ""))
        if category == "truncated_response" or "finish_reason=length" in message:
            truncated += 1
        if category in {"invalid_json", "truncated_response"} or "not valid JSON" in message:
            invalid_json += 1
        if category == "timeout" or "timed out" in message.lower():
            timeouts += 1
    denominator = attempted or 1
    return ReliabilityMetrics(
        attempted_clauses=attempted,
        successful_predictions=successful,
        failed_responses=failures,
        truncated_responses=truncated,
        invalid_json_responses=invalid_json,
        timeout_responses=timeouts,
        prediction_success_rate=successful / denominator,
        json_validity_rate=(attempted - invalid_json) / denominator,
        truncation_rate=truncated / denominator,
    )


def _load_predictions(run_directory: Path) -> dict[str, SemanticRoleSelection]:
    predictions: dict[str, SemanticRoleSelection] = {}
    for path in sorted(run_directory.rglob("evaluation.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        candidate = ClauseEvaluationAnnotation.model_validate(payload["annotation_candidate"])
        key = candidate.clause.key
        if key in predictions:
            raise ValueError(f"duplicate prediction for {key}: {path}")
        predictions[key] = candidate.proposal
    return predictions


def _structure_selection(strata: dict[str, str]) -> SemanticRoleSelection | None:
    raw = strata.get("semantic_role") or strata.get("role") or strata.get("semantic_roles")
    if not raw or raw in {"none", "unclassified", "unknown"}:
        return None
    values = [value.strip() for value in raw.replace(";", ",").split(",") if value.strip()]
    try:
        roles = tuple(SemanticRole(value) for value in values)
    except ValueError:
        return None
    if not roles:
        return None
    return SemanticRoleSelection(semantic_roles=roles, primary_role=roles[0])


def _silver_expected(row: _Row) -> SemanticRoleSelection | None:
    if row.resolved is not None:
        if row.resolved.annotation is not None:
            return row.resolved.annotation
        return row.resolved.proposal
    return row.structure


def _agreement(
    pairs: Iterable[tuple[SemanticRoleSelection, SemanticRoleSelection]], *, eligible: int
) -> AgreementMetrics:
    items = list(pairs)
    tp = fp = fn = exact = primary = 0
    role_scores: list[float] = []
    for predicted, expected in items:
        p = set(predicted.semantic_roles)
        e = set(expected.semantic_roles)
        tp += len(p & e)
        fp += len(p - e)
        fn += len(e - p)
        exact += p == e
        primary += predicted.primary_role == expected.primary_role
        for role in SemanticRole:
            rtp = int(role in p and role in e)
            rfp = int(role in p and role not in e)
            rfn = int(role not in p and role in e)
            denom = 2 * rtp + rfp + rfn
            if denom:
                role_scores.append(2 * rtp / denom)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    count = len(items)
    return AgreementMetrics(
        eligible=eligible,
        evaluated=count,
        coverage=count / eligible if eligible else 0.0,
        exact_match_rate=exact / count if count else 0.0,
        primary_role_accuracy=primary / count if count else 0.0,
        micro_precision=precision if count else 0.0,
        micro_recall=recall if count else 0.0,
        micro_f1=f1 if count else 0.0,
        macro_f1=sum(role_scores) / len(role_scores) if role_scores else 0.0,
    )


def _confusion(
    pairs: Iterable[tuple[SemanticRoleSelection, SemanticRoleSelection]],
) -> tuple[ConfusionEntry, ...]:
    counts: Counter[tuple[str, str]] = Counter()
    for predicted, expected in pairs:
        exp = expected.primary_role.value if expected.primary_role else "<none>"
        pred = predicted.primary_role.value if predicted.primary_role else "<none>"
        counts[(exp, pred)] += 1
    return tuple(
        ConfusionEntry(expected=e, predicted=p, count=count)
        for (e, p), count in sorted(counts.items())
    )


def _calibration(
    pairs: Iterable[tuple[SemanticRoleSelection, SemanticRoleSelection]],
) -> CalibrationMetrics:
    entries = [
        (pred.confidence, int(set(pred.semantic_roles) == set(exp.semantic_roles)))
        for pred, exp in pairs
        if pred.confidence is not None
    ]
    total = len(list(pairs)) if not isinstance(pairs, list) else len(pairs)
    bins: list[CalibrationBin] = []
    weighted_error = 0.0
    for index in range(10):
        lower, upper = index / 10, (index + 1) / 10
        bucket = [
            (confidence, accuracy)
            for confidence, accuracy in entries
            if lower <= confidence <= upper and (index == 9 or confidence < upper)
        ]
        if bucket:
            mean = sum(c for c, _ in bucket) / len(bucket)
            accuracy = sum(a for _, a in bucket) / len(bucket)
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
        coverage=len(entries) / total if total else 0.0,
        brier_score=(sum((c - a) ** 2 for c, a in entries) / len(entries)) if entries else None,
        expected_calibration_error=weighted_error / len(entries) if entries else None,
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
    gold_states = {
        AnnotationLifecycleStatus.REVIEWED,
        AnnotationLifecycleStatus.PUBLISHED,
    }
    for (dimension, value), group in sorted(grouped.items()):
        gold = [
            (row.prediction, row.resolved.annotation)
            for row in group
            if row.prediction
            and row.resolved
            and row.resolved.annotation
            and row.resolved.lifecycle_status in gold_states
        ]
        silver = [
            (row.prediction, expected)
            for row in group
            if row.prediction and (expected := _silver_expected(row))
        ]
        structure = [
            (row.prediction, row.structure) for row in group if row.prediction and row.structure
        ]
        gold_eligible = sum(
            row.resolved is not None
            and row.resolved.annotation is not None
            and row.resolved.lifecycle_status in gold_states
            for row in group
        )
        reports.append(
            EvaluationSliceReport(
                dimension=dimension,
                value=value,
                cases=len(group),
                gold=_agreement(gold, eligible=gold_eligible),
                silver=_agreement(
                    silver,
                    eligible=sum(_silver_expected(row) is not None for row in group),
                ),
                structure=_agreement(
                    structure,
                    eligible=sum(row.structure is not None for row in group),
                ),
            )
        )
    return tuple(reports)


def _markdown(report: AnnotationQualificationReport) -> str:
    def agreement_line(name: str, metric: AgreementMetrics) -> str:
        values = (
            name,
            f"{metric.evaluated}/{metric.eligible}",
            f"{metric.exact_match_rate:.3f}",
            f"{metric.primary_role_accuracy:.3f}",
            f"{metric.micro_f1:.3f}",
            f"{metric.macro_f1:.3f}",
        )
        return "| " + " | ".join(values) + " |"

    brier = report.calibration.brier_score
    calibration_error = report.calibration.expected_calibration_error
    lines = [
        f"# Annotation qualification: {report.corpus_id}",
        "",
        f"Generated: `{report.generated_at.isoformat()}`",
        "",
        "## Coverage",
        "",
        f"- Corpus clauses: {report.coverage.corpus_clauses}",
        f"- Predictions: {report.coverage.predictions}",
        f"- Published gold: {report.coverage.published_gold}",
        f"- Local reviewed gold: {report.coverage.local_reviewed_gold}",
        f"- Local proposals: {report.coverage.local_proposals}",
        f"- Structure labels: {report.coverage.structure_labels}",
        f"- Missing predictions: {report.coverage.missing_predictions}",
        "",
        "## Reliability",
        "",
        f"- Attempted clauses: {report.reliability.attempted_clauses}",
        f"- Successful predictions: {report.reliability.successful_predictions}",
        f"- Failed responses: {report.reliability.failed_responses}",
        f"- Truncated responses: {report.reliability.truncated_responses}",
        f"- Invalid JSON responses: {report.reliability.invalid_json_responses}",
        f"- Timeout responses: {report.reliability.timeout_responses}",
        f"- Prediction success rate: {report.reliability.prediction_success_rate:.3f}",
        f"- JSON validity rate: {report.reliability.json_validity_rate:.3f}",
        f"- Truncation rate: {report.reliability.truncation_rate:.3f}",
        "",
        "## Agreement",
        "",
        "| Evidence | Evaluated | Exact | Primary accuracy | Micro-F1 | Macro-F1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        agreement_line("Gold", report.gold_agreement),
        agreement_line("Silver", report.silver_agreement),
        agreement_line("Structure", report.structure_agreement),
        "",
        "## Calibration",
        "",
        f"- Confidence coverage: {report.calibration.coverage:.3f}",
        f"- Brier score: {brier if brier is not None else 'n/a'}",
        "- Expected calibration error: "
        f"{calibration_error if calibration_error is not None else 'n/a'}",
        "",
        "## Primary-role confusion",
        "",
        "| Expected | Predicted | Count |",
        "| --- | --- | ---: |",
    ]
    lines.extend(
        f"| {entry.expected} | {entry.predicted} | {entry.count} |"
        for entry in report.primary_role_confusion
    )
    lines.extend(
        [
            "",
            "## Slice results",
            "",
            "| Dimension | Value | Cases | Gold F1 | Silver F1 | Structure F1 |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report.slices:
        values = (
            item.dimension,
            item.value,
            str(item.cases),
            f"{item.gold.micro_f1:.3f}",
            f"{item.silver.micro_f1:.3f}",
            f"{item.structure.micro_f1:.3f}",
        )
        lines.append("| " + " | ".join(values) + " |")
    if report.diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        lines.extend(f"- {item}" for item in report.diagnostics)
    return "\n".join(lines) + "\n"
