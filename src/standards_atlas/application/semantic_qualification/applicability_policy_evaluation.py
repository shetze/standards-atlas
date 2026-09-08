"""Golden-corpus evaluation for deterministic applicability policy replay reports."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
    ApplicabilityModelMetrics,
)
from standards_atlas.application.semantic_qualification.applicability_policy_replay import (
    ApplicabilityPolicyReplayReport,
)


class ApplicabilityPolicyEvaluationCase(BaseModel):
    """One published golden case matched to a replay decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    expected_present: bool
    gate_present: bool
    final_present: bool | None
    error: Literal["false_positive", "false_negative"] | None = None

    @model_validator(mode="after")
    def validate_error(self) -> ApplicabilityPolicyEvaluationCase:
        expected_error = None
        if self.final_present is not None and self.final_present != self.expected_present:
            expected_error = "false_negative" if self.expected_present else "false_positive"
        if self.error != expected_error:
            raise ValueError("policy evaluation error does not match the decision")
        return self


class ApplicabilityPolicyEvaluationReport(BaseModel):
    """Error-budget qualification result for one replay and one golden corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    golden_corpus_id: str = Field(min_length=1)
    golden_corpus_version: str = Field(min_length=1)
    published_cases: int = Field(ge=0)
    matched_cases: int = Field(ge=0)
    missing_cases: tuple[str, ...] = ()
    unknown_cases: tuple[str, ...] = ()
    metrics: ApplicabilityModelMetrics
    max_false_positive: int = Field(ge=0)
    max_false_negative: int = Field(ge=0)
    passed: bool
    cases: tuple[ApplicabilityPolicyEvaluationCase, ...]

    @model_validator(mode="after")
    def validate_accounting(self) -> ApplicabilityPolicyEvaluationReport:
        if self.matched_cases + len(self.missing_cases) != self.published_cases:
            raise ValueError("matched and missing golden cases do not balance")
        if len(self.cases) != self.matched_cases:
            raise ValueError("matched_cases must match evaluation cases")
        resolved = self.matched_cases - len(self.unknown_cases)
        if self.metrics.evaluated_cases != resolved:
            raise ValueError("metrics must cover exactly the resolved golden cases")
        expected_pass = (
            not self.missing_cases
            and not self.unknown_cases
            and self.metrics.false_positive <= self.max_false_positive
            and self.metrics.false_negative <= self.max_false_negative
        )
        if self.passed != expected_pass:
            raise ValueError("passed does not match the configured error budget")
        return self


def evaluate_applicability_policy(
    golden: ApplicabilityGoldenCorpus,
    replay: ApplicabilityPolicyReplayReport,
    *,
    max_false_positive: int = 2,
    max_false_negative: int = 2,
) -> ApplicabilityPolicyEvaluationReport:
    """Evaluate one replay against published gold without feeding labels into replay."""

    published = tuple(
        case for case in golden.cases if case.status == "published" and case.expected is not None
    )
    if not published:
        raise ValueError("applicability golden corpus contains no published cases")

    replay_by_coordinate = {(item.document_key, item.clause_id): item for item in replay.cases}
    if len(replay_by_coordinate) != len(replay.cases):
        raise ValueError("applicability policy replay coordinates must be unique")

    missing: list[str] = []
    unknown: list[str] = []
    resolved_predictions: list[tuple[bool, bool]] = []
    cases: list[ApplicabilityPolicyEvaluationCase] = []

    for golden_case in published:
        expected = golden_case.expected
        assert expected is not None
        coordinate = (golden_case.document_key, golden_case.clause_id)
        replay_case = replay_by_coordinate.get(coordinate)
        if replay_case is None:
            missing.append(f"{golden_case.document_key}/{golden_case.clause_id}")
            continue
        if replay_case.final_present is None:
            unknown.append(f"{golden_case.document_key}/{golden_case.clause_id}")
        else:
            resolved_predictions.append((replay_case.final_present, expected.present))
        error = None
        if replay_case.final_present is not None and replay_case.final_present != expected.present:
            error = "false_negative" if expected.present else "false_positive"
        cases.append(
            ApplicabilityPolicyEvaluationCase(
                document_key=golden_case.document_key,
                clause_id=golden_case.clause_id,
                reference=golden_case.reference,
                expected_present=expected.present,
                gate_present=replay_case.gate_present,
                final_present=replay_case.final_present,
                error=error,
            )
        )

    metrics = _metrics(resolved_predictions)
    passed = (
        not missing
        and not unknown
        and metrics.false_positive <= max_false_positive
        and metrics.false_negative <= max_false_negative
    )
    return ApplicabilityPolicyEvaluationReport(
        policy_id=replay.policy_id,
        policy_version=replay.policy_version,
        golden_corpus_id=golden.corpus_id,
        golden_corpus_version=golden.corpus_version,
        published_cases=len(published),
        matched_cases=len(cases),
        missing_cases=tuple(missing),
        unknown_cases=tuple(unknown),
        metrics=metrics,
        max_false_positive=max_false_positive,
        max_false_negative=max_false_negative,
        passed=passed,
        cases=tuple(cases),
    )


def evaluate_applicability_policy_files(
    *,
    golden_path: Path,
    replay_path: Path,
    max_false_positive: int = 2,
    max_false_negative: int = 2,
) -> ApplicabilityPolicyEvaluationReport:
    golden = ApplicabilityGoldenCorpus.load(golden_path)
    replay = ApplicabilityPolicyReplayReport.load(replay_path)
    return evaluate_applicability_policy(
        golden,
        replay,
        max_false_positive=max_false_positive,
        max_false_negative=max_false_negative,
    )


def _metrics(predictions: list[tuple[bool, bool]]) -> ApplicabilityModelMetrics:
    tp = sum(predicted and expected for predicted, expected in predictions)
    fp = sum(predicted and not expected for predicted, expected in predictions)
    tn = sum(not predicted and not expected for predicted, expected in predictions)
    fn = sum(not predicted and expected for predicted, expected in predictions)
    total = len(predictions)
    predicted_positive = tp + fp
    actual_positive = tp + fn
    actual_negative = tn + fp
    precision = tp / predicted_positive if predicted_positive else 0.0
    recall = tp / actual_positive if actual_positive else 0.0
    specificity = tn / actual_negative if actual_negative else 0.0
    accuracy = (tp + tn) / total if total else 0.0
    balanced = (recall + specificity) / 2 if total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return ApplicabilityModelMetrics(
        model_id="applicability_policy",
        evaluated_cases=total,
        predicted_positive_cases=predicted_positive,
        predicted_positive_rate=predicted_positive / total if total else 0.0,
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        presence_accuracy=accuracy,
        presence_precision=precision,
        presence_recall=recall,
        presence_specificity=specificity,
        presence_balanced_accuracy=balanced,
        presence_f1=f1,
    )
