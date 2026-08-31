"""Focused HITL golden-set support for applicability presence qualification."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal
from zipfile import ZipFile

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.applicability_contract import (
    ApplicabilityPolarity,
)
from standards_atlas.application.semantic_qualification.applicability_hard_cases import (
    PREDICTION_SNAPSHOT_FILENAME,
    ApplicabilityPrediction,
    ApplicabilityPredictionSnapshot,
    _baseline,
    _collapsed_predictions,
    _dataset_details,
    _find_member,
)


class ApplicabilityGoldenExpected(BaseModel):
    """Human-reviewed applicability reference for one clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    present: bool
    polarity: ApplicabilityPolarity | None = None

    @model_validator(mode="after")
    def polarity_requires_presence(self) -> ApplicabilityGoldenExpected:
        if self.polarity is not None and not self.present:
            raise ValueError("applicability polarity requires present=true")
        return self


class ApplicabilityGoldenCase(BaseModel):
    """One selected applicability hard case and optional published reference."""

    model_config = ConfigDict(frozen=True)

    clause_id: str
    document_key: str
    reference: str
    text: str
    category: str = "presence_disagreement"
    status: Literal["proposed", "published", "rejected"] = "proposed"
    expected: ApplicabilityGoldenExpected | None = None


class ApplicabilityGoldenCorpus(BaseModel):
    """Small run-derived applicability golden set."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    corpus_id: str = "applicability-hard-cases"
    corpus_version: str = "2.0.0"
    source_archive: str
    source_archive_sha256: str
    cases: tuple[ApplicabilityGoldenCase, ...]

    @model_validator(mode="after")
    def case_keys_must_be_unique(self) -> ApplicabilityGoldenCorpus:
        keys = [(case.document_key, case.clause_id) for case in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("applicability golden corpus case keys must be unique")
        return self

    @classmethod
    def load(cls, path: Path) -> ApplicabilityGoldenCorpus:
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


class ApplicabilityCorpusBuildResult(BaseModel):
    """Artifacts written by the run-derived applicability hard-case builder."""

    model_config = ConfigDict(frozen=True)

    review_path: Path
    review_guide_path: Path
    golden_path: Path
    selected_count: int
    review_created: bool


class ApplicabilityModelMetrics(BaseModel):
    """Presence and polarity diagnostics against published applicability gold cases."""

    model_config = ConfigDict(frozen=True)

    model_id: str
    evaluated_cases: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    true_negative: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    presence_accuracy: float = Field(ge=0.0, le=1.0)
    presence_precision: float = Field(ge=0.0, le=1.0)
    presence_recall: float = Field(ge=0.0, le=1.0)
    presence_specificity: float = Field(ge=0.0, le=1.0)
    presence_balanced_accuracy: float = Field(ge=0.0, le=1.0)
    presence_f1: float = Field(ge=0.0, le=1.0)
    polarity_end_to_end_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    polarity_accuracy_given_presence: float | None = Field(default=None, ge=0.0, le=1.0)


class ApplicabilityCaseError(BaseModel):
    """One false presence prediction with enough context for HITL diagnosis."""

    model_config = ConfigDict(frozen=True)

    evaluator_id: str
    document_key: str
    clause_id: str
    reference: str
    expected_present: bool
    predicted_present: bool
    error: Literal["false_positive", "false_negative"]
    presence_votes: dict[str, bool] = Field(default_factory=dict)


class ApplicabilityEnsembleMetrics(BaseModel):
    """Offline majority-vote candidate evaluated without changing production consensus."""

    model_config = ConfigDict(frozen=True)

    ensemble_id: str
    model_ids: tuple[str, ...]
    metrics: ApplicabilityModelMetrics


class ApplicabilityGoldenRegressionReport(BaseModel):
    """Offline calibration report against the applicability golden set."""

    model_config = ConfigDict(frozen=True)

    published_cases: int = Field(ge=0)
    positive_cases: int = Field(ge=0)
    negative_cases: int = Field(ge=0)
    baseline_majority: ApplicabilityModelMetrics
    models: tuple[ApplicabilityModelMetrics, ...]
    ensembles: tuple[ApplicabilityEnsembleMetrics, ...] = ()
    errors: tuple[ApplicabilityCaseError, ...] = ()


def build_applicability_golden_review(
    run_archive: Path,
    review_root: Path = Path("local/review"),
    *,
    limit: int = 30,
) -> ApplicabilityCorpusBuildResult:
    """Create a flat HITL review from final applicability-presence disagreements."""
    report, manifest = _load_run_inputs(run_archive)
    presence_eligibility = {
        str(model.get("id")): bool(
            (model.get("dimension_eligibility") or {}).get("applicability_presence", True)
        )
        for model in manifest.get("models", [])
    }
    polarity_eligibility = {
        str(model.get("id")): bool(
            (model.get("dimension_eligibility") or {}).get("applicability_polarity", True)
        )
        for model in manifest.get("models", [])
    }
    cases: list[ApplicabilityGoldenCase] = []
    for clause in report.get("clauses", []):
        votes = list(clause.get("votes", []))
        presence_votes = [
            vote for vote in votes if presence_eligibility.get(str(vote.get("model_id")), True)
        ]
        presence_values = {bool(vote.get("applicability_present")) for vote in presence_votes}
        category = None
        if len(presence_values) > 1:
            category = "presence_disagreement"
        else:
            polarity_values = {
                vote.get("applicability_polarity")
                for vote in votes
                if bool(vote.get("applicability_present"))
                and polarity_eligibility.get(str(vote.get("model_id")), True)
                and vote.get("applicability_polarity") is not None
            }
            if len(polarity_values) > 1:
                category = "polarity_disagreement"
        if category is None:
            continue
        cases.append(
            ApplicabilityGoldenCase(
                clause_id=str(clause["clause_id"]),
                document_key=str(clause["document_key"]),
                reference=_qualified_reference(clause),
                text=str(clause.get("clause_text") or ""),
                category=category,
            )
        )
    cases.sort(key=lambda case: (case.document_key, case.reference, case.clause_id))
    cases = cases[:limit]
    if not cases:
        raise ValueError("qualification run contains no applicability presence disagreements")

    review_dir = review_root / "applicability" / "2.0.0"
    review_path = review_dir / "applicability-golden-review.csv"
    review_created = False
    if not review_path.exists():
        review_dir.mkdir(parents=True, exist_ok=True)
        _write_review_csv(review_path, tuple(cases))
        review_created = True
    review_guide_path = review_dir / "README.md"
    _write_review_guide(review_guide_path)
    return ApplicabilityCorpusBuildResult(
        review_path=review_path,
        review_guide_path=review_guide_path,
        golden_path=review_dir / "applicability-golden-corpus.yaml",
        selected_count=len(cases),
        review_created=review_created,
    )


def publish_applicability_golden_review(
    review_path: Path,
    run_archive: Path,
    output_path: Path,
) -> ApplicabilityGoldenCorpus:
    """Compile published HITL rows into a machine-readable golden set."""
    with review_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    published: list[ApplicabilityGoldenCase] = []
    for row in rows:
        status = (row.get("review_status") or "pending").strip().lower()
        if status != "published":
            continue
        present = _parse_bool(row.get("present"))
        if present is None:
            raise ValueError("published applicability rows require present")
        polarity = (row.get("polarity") or "").strip() or None
        published.append(
            ApplicabilityGoldenCase(
                clause_id=(row.get("clause_id") or "").strip(),
                document_key=(row.get("document_key") or "").strip(),
                reference=(row.get("reference") or "").strip(),
                text=row.get("text") or "",
                category=(row.get("category") or "presence_disagreement").strip(),
                status="published",
                expected=ApplicabilityGoldenExpected(
                    present=present,
                    polarity=polarity,
                ),
            )
        )
    if not published:
        raise ValueError("applicability review contains no published cases")
    corpus = ApplicabilityGoldenCorpus(
        source_archive=run_archive.name,
        source_archive_sha256=_sha256(run_archive),
        cases=tuple(published),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(corpus.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return corpus


def evaluate_applicability_golden_corpus(
    golden: ApplicabilityGoldenCorpus,
    run_archive: Path,
) -> ApplicabilityGoldenRegressionReport:
    """Measure baseline majority, models, and offline ensembles against HITL gold."""
    report, _ = _load_run_inputs(run_archive)
    clauses = {
        (str(item.get("document_key")), str(item.get("clause_id"))): item
        for item in report.get("clauses", [])
    }
    published = tuple(
        case for case in golden.cases if case.status == "published" and case.expected is not None
    )
    if not published:
        raise ValueError("applicability golden corpus contains no published cases")

    baseline_predictions: list[tuple[bool, str | None, ApplicabilityGoldenExpected]] = []
    model_predictions: dict[str, list[tuple[bool, str | None, ApplicabilityGoldenExpected]]] = {}
    case_votes: dict[tuple[str, str], dict[str, tuple[bool, str | None]]] = {}
    matched_cases: list[ApplicabilityGoldenCase] = []
    for case in published:
        clause = clauses.get((case.document_key, case.clause_id))
        if clause is None:
            continue
        matched_cases.append(case)
        expected = case.expected
        assert expected is not None
        baseline_present = clause.get("applicability_present")
        if baseline_present is not None:
            baseline_predictions.append(
                (bool(baseline_present), clause.get("applicability_polarity"), expected)
            )
        votes: dict[str, tuple[bool, str | None]] = {}
        for vote in clause.get("votes", []):
            model_id = str(vote.get("model_id"))
            prediction = (
                bool(vote.get("applicability_present")),
                vote.get("applicability_polarity"),
            )
            votes[model_id] = prediction
            model_predictions.setdefault(model_id, []).append((*prediction, expected))
        case_votes[(case.document_key, case.clause_id)] = votes

    ensemble_specs = _available_ensemble_specs(set(model_predictions))
    ensemble_predictions: dict[str, list[tuple[bool, str | None, ApplicabilityGoldenExpected]]] = {
        ensemble_id: [] for ensemble_id, _ in ensemble_specs
    }
    ensemble_models = dict(ensemble_specs)
    for case in matched_cases:
        expected = case.expected
        assert expected is not None
        votes = case_votes[(case.document_key, case.clause_id)]
        for ensemble_id, model_ids in ensemble_specs:
            selected = [votes.get(model_id) for model_id in model_ids]
            if any(prediction is None for prediction in selected):
                continue
            resolved = _offline_majority(tuple(prediction for prediction in selected if prediction))
            if resolved is not None:
                ensemble_predictions[ensemble_id].append((*resolved, expected))

    errors: list[ApplicabilityCaseError] = []
    for case in matched_cases:
        expected = case.expected
        assert expected is not None
        clause = clauses[(case.document_key, case.clause_id)]
        votes = case_votes[(case.document_key, case.clause_id)]
        presence_votes = {model_id: value[0] for model_id, value in sorted(votes.items())}
        baseline_present = clause.get("applicability_present")
        if baseline_present is not None:
            _append_presence_error(
                errors, "baseline_majority", case, expected, bool(baseline_present), presence_votes
            )
        for model_id, (predicted_present, _) in sorted(votes.items()):
            _append_presence_error(
                errors, model_id, case, expected, predicted_present, presence_votes
            )
        for ensemble_id, model_ids in ensemble_specs:
            selected = [votes.get(model_id) for model_id in model_ids]
            if any(prediction is None for prediction in selected):
                continue
            resolved = _offline_majority(tuple(prediction for prediction in selected if prediction))
            if resolved is not None:
                _append_presence_error(
                    errors, ensemble_id, case, expected, resolved[0], presence_votes
                )

    positive_cases = sum(bool(case.expected and case.expected.present) for case in published)
    return ApplicabilityGoldenRegressionReport(
        published_cases=len(published),
        positive_cases=positive_cases,
        negative_cases=len(published) - positive_cases,
        baseline_majority=_metrics("baseline_majority", baseline_predictions),
        models=tuple(
            _metrics(model_id, predictions)
            for model_id, predictions in sorted(model_predictions.items())
        ),
        ensembles=tuple(
            ApplicabilityEnsembleMetrics(
                ensemble_id=ensemble_id,
                model_ids=ensemble_models[ensemble_id],
                metrics=_metrics(ensemble_id, ensemble_predictions[ensemble_id]),
            )
            for ensemble_id, _ in ensemble_specs
        ),
        errors=tuple(errors),
    )


def _available_ensemble_specs(available: set[str]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    candidates = (
        (
            "mistral-q4-q6-ministral",
            (
                "mistral-small-3.2-24b-instruct-q4-k-m",
                "mistral-small-3.2-24b-instruct-q6-k",
                "ministral-3-8b-instruct-2512-q4-k-m",
            ),
        ),
        (
            "mistral-q4-q6",
            (
                "mistral-small-3.2-24b-instruct-q4-k-m",
                "mistral-small-3.2-24b-instruct-q6-k",
            ),
        ),
        ("mistral-q4", ("mistral-small-3.2-24b-instruct-q4-k-m",)),
    )
    return tuple(spec for spec in candidates if set(spec[1]) <= available)


def _offline_majority(
    predictions: tuple[tuple[bool, str | None], ...],
) -> tuple[bool, str | None] | None:
    present = sum(prediction[0] for prediction in predictions)
    absent = len(predictions) - present
    if present == absent:
        return None
    resolved_present = present > absent
    if not resolved_present:
        return False, None
    polarities = Counter(
        _qualification_polarity(prediction[1])
        for prediction in predictions
        if prediction[0] and prediction[1]
    )
    if not polarities:
        return True, None
    ranked = polarities.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return True, None
    polarity = ranked[0][0]
    return True, polarity.value if polarity is not None else None


def _append_presence_error(
    errors: list[ApplicabilityCaseError],
    evaluator_id: str,
    case: ApplicabilityGoldenCase,
    expected: ApplicabilityGoldenExpected,
    predicted_present: bool,
    presence_votes: dict[str, bool],
) -> None:
    if predicted_present == expected.present:
        return
    errors.append(
        ApplicabilityCaseError(
            evaluator_id=evaluator_id,
            document_key=case.document_key,
            clause_id=case.clause_id,
            reference=case.reference,
            expected_present=expected.present,
            predicted_present=predicted_present,
            error="false_negative" if expected.present else "false_positive",
            presence_votes=presence_votes,
        )
    )


def _metrics(
    model_id: str,
    predictions: list[tuple[bool, str | None, ApplicabilityGoldenExpected]],
) -> ApplicabilityModelMetrics:
    tp = fp = tn = fn = 0
    polarity_end_to_end_total = polarity_end_to_end_correct = 0
    polarity_given_presence_total = polarity_given_presence_correct = 0
    for predicted_present, predicted_polarity, expected in predictions:
        if expected.present and predicted_present:
            tp += 1
        elif expected.present:
            fn += 1
        elif predicted_present:
            fp += 1
        else:
            tn += 1
        if expected.present and expected.polarity is not None:
            polarity_end_to_end_total += 1
            polarity_end_to_end_correct += (
                _qualification_polarity(predicted_polarity) == expected.polarity
            )
            if predicted_present:
                polarity_given_presence_total += 1
                polarity_given_presence_correct += (
                    _qualification_polarity(predicted_polarity) == expected.polarity
                )
    precision = _ratio(tp, tp + fp, empty=1.0)
    recall = _ratio(tp, tp + fn, empty=1.0)
    specificity = _ratio(tn, tn + fp, empty=1.0)
    total = tp + fp + tn + fn
    return ApplicabilityModelMetrics(
        model_id=model_id,
        evaluated_cases=total,
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        presence_accuracy=_ratio(tp + tn, total, empty=0.0),
        presence_precision=precision,
        presence_recall=recall,
        presence_specificity=specificity,
        presence_balanced_accuracy=(recall + specificity) / 2,
        presence_f1=_f1(precision, recall),
        polarity_end_to_end_accuracy=(
            polarity_end_to_end_correct / polarity_end_to_end_total
            if polarity_end_to_end_total
            else None
        ),
        polarity_accuracy_given_presence=(
            polarity_given_presence_correct / polarity_given_presence_total
            if polarity_given_presence_total
            else None
        ),
    )


def _load_run_inputs(run_archive: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    with ZipFile(run_archive) as archive:
        manifest = yaml.safe_load(archive.read("configuration/qualification-manifest.yaml")) or {}
        snapshot_name = _find_member(archive, PREDICTION_SNAPSHOT_FILENAME)
        if snapshot_name is None:
            raise ValueError(
                "qualification run does not contain clause-level applicability predictions; "
                "rerun qualification with the current archive schema"
            )
        snapshot = ApplicabilityPredictionSnapshot.model_validate_json(archive.read(snapshot_name))
        dataset = json.loads(archive.read("inputs/corpus/dataset.json"))

    presence_eligible = {
        str(model.get("id"))
        for model in manifest.get("models", [])
        if bool((model.get("dimension_eligibility") or {}).get("applicability_presence", True))
    }
    polarity_eligible = {
        str(model.get("id"))
        for model in manifest.get("models", [])
        if bool((model.get("dimension_eligibility") or {}).get("applicability_polarity", True))
    }
    baseline_prompt, baseline_frame = _baseline(snapshot)
    baseline = _collapsed_predictions(
        snapshot,
        prompt_id=baseline_prompt,
        cbox_frame=baseline_frame,
        eligible=presence_eligible,
    )
    details = _dataset_details(dataset)
    clause_keys = sorted({key for predictions in baseline.values() for key in predictions})
    clauses: list[dict[str, Any]] = []
    for clause_key in clause_keys:
        votes = {
            model_id: predictions[clause_key]
            for model_id, predictions in baseline.items()
            if clause_key in predictions
        }
        if not votes:
            continue
        first = next(iter(votes.values()))
        reference, text = details.get(
            (first.document_key, first.clause_id),
            (first.clause_id, ""),
        )
        consensus_present = _presence_consensus(tuple(votes.values()))
        consensus_polarity = (
            _polarity_consensus(votes, eligible=polarity_eligible)
            if consensus_present is True
            else None
        )
        clauses.append(
            {
                "clause_id": first.clause_id,
                "document_key": first.document_key,
                "reference": reference,
                "clause_text": text,
                "applicability_present": consensus_present,
                "applicability_polarity": consensus_polarity,
                "votes": [
                    {
                        "model_id": model_id,
                        "applicability_present": prediction.present,
                        "applicability_polarity": prediction.polarity,
                    }
                    for model_id, prediction in sorted(votes.items())
                ],
            }
        )
    return {"clauses": clauses}, manifest


def _presence_consensus(predictions: tuple[ApplicabilityPrediction, ...]) -> bool | None:
    present = sum(prediction.present for prediction in predictions)
    absent = len(predictions) - present
    if present == absent:
        return None
    return present > absent


def _polarity_consensus(
    predictions: dict[str, ApplicabilityPrediction],
    *,
    eligible: set[str],
) -> str | None:
    counts = Counter(
        prediction.polarity
        for model_id, prediction in predictions.items()
        if model_id in eligible and prediction.present and prediction.polarity is not None
    )
    if not counts:
        return None
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def _qualified_reference(clause: dict[str, Any]) -> str:
    document_key = str(clause.get("document_key") or "").strip()
    reference = str(clause.get("reference") or "").strip()
    if reference.startswith(f"{document_key}:"):
        return reference
    return f"{document_key}:{reference}" if reference else document_key


def _write_review_csv(path: Path, cases: tuple[ApplicabilityGoldenCase, ...]) -> None:
    fields = (
        "document_key",
        "reference",
        "category",
        "text",
        "review_status",
        "present",
        "polarity",
        "review_note",
        "clause_id",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "document_key": case.document_key,
                    "reference": case.reference,
                    "category": case.category,
                    "text": case.text,
                    "review_status": "pending",
                    "present": "",
                    "polarity": "",
                    "review_note": "",
                    "clause_id": case.clause_id,
                }
            )


def _write_review_guide(path: Path) -> None:
    path.write_text(
        "# Applicability Golden Review\n\n"
        "Review only the semantic applicability of each clause. Set "
        "`review_status=published` when complete.\n\n"
        "`present` is `true` only when the clause explicitly changes whether normative content "
        "is in force. Conditions that only change how an activity, method, analysis, design, "
        "calculation, or process is performed are not applicability.\n\n"
        "When `present=true`, set `polarity` to `included` when the normative content is in "
        "scope and to `excluded` when it is explicitly out of scope. Leave `polarity` empty "
        "only when presence is clear but the direction is genuinely uncertain. Exceptions and "
        "generic condition semantics are deliberately outside this qualification stage.\n",
        encoding="utf-8",
    )


def _parse_bool(value: str | None) -> bool | None:
    normalized = (value or "").strip().lower()
    if not normalized:
        return None
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def _qualification_polarity(value: str | None) -> ApplicabilityPolarity | None:
    return ApplicabilityPolarity(value) if value is not None else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _ratio(numerator: int, denominator: int, *, empty: float) -> float:
    return numerator / denominator if denominator else empty


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0
