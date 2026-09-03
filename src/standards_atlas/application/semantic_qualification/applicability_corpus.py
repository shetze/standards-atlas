"""Focused HITL golden-set support for applicability presence qualification."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal
from zipfile import ZipFile

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.applicability_hard_cases import (
    PREDICTION_SNAPSHOT_FILENAME,
    ApplicabilityPrediction,
    ApplicabilityPredictionSnapshot,
    PresenceHardCase,
    _baseline,
    _case_rank,
    _collapsed_predictions,
    _dataset_details,
    _find_member,
    _presence_eligible_model_ids,
    _review_candidate,
    load_applicability_prediction_snapshot,
    project_applicability_hard_cases,
)


class ApplicabilityGoldenExpected(BaseModel):
    """Human-reviewed presence reference for one clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    present: bool


class ApplicabilityGoldenProvenance(BaseModel):
    """Immutable source-run provenance for one published gold case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_archive: str
    source_archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ApplicabilityGoldenCase(BaseModel):
    """One selected applicability hard case and optional published presence reference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: str
    document_key: str
    reference: str
    text: str
    category: str
    status: Literal["proposed", "published", "rejected"] = "proposed"
    expected: ApplicabilityGoldenExpected | None = None
    provenance: ApplicabilityGoldenProvenance | None = None

    @model_validator(mode="after")
    def published_requires_reference_and_provenance(self) -> ApplicabilityGoldenCase:
        if self.status == "published" and (self.expected is None or self.provenance is None):
            raise ValueError("published applicability gold cases require expected and provenance")
        return self


class ApplicabilityGoldenCorpus(BaseModel):
    """Incremental presence-only applicability hard-case golden corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["3.0"] = "3.0"
    corpus_id: str = "applicability-hard-cases"
    corpus_version: str = "3.0.0"
    cases: tuple[ApplicabilityGoldenCase, ...]

    @model_validator(mode="after")
    def case_keys_must_be_unique(self) -> ApplicabilityGoldenCorpus:
        keys = [(case.document_key, case.clause_id) for case in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("applicability golden corpus case keys must be unique")
        return self

    @classmethod
    def load(cls, path: Path) -> ApplicabilityGoldenCorpus:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict) and raw.get("schema_version") == "2.1":
            raise ValueError(
                "applicability golden corpus schema 2.1 must be migrated to presence-only "
                "schema 3.0 with `standards-atlas evaluation applicability-corpus-migrate`"
            )
        return cls.model_validate(raw)


class _LegacyApplicabilityGoldenExpected(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    present: bool
    polarity: Literal["included", "excluded"] | None = None

    @model_validator(mode="after")
    def polarity_requires_presence(self) -> _LegacyApplicabilityGoldenExpected:
        if self.polarity is not None and not self.present:
            raise ValueError("legacy applicability polarity requires present=true")
        return self


class _LegacyApplicabilityGoldenCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: str
    document_key: str
    reference: str
    text: str
    category: str
    status: Literal["proposed", "published", "rejected"] = "proposed"
    expected: _LegacyApplicabilityGoldenExpected | None = None
    provenance: ApplicabilityGoldenProvenance | None = None

    @model_validator(mode="after")
    def published_requires_reference_and_provenance(self) -> _LegacyApplicabilityGoldenCase:
        if self.status == "published" and (self.expected is None or self.provenance is None):
            raise ValueError("published legacy applicability cases require expected and provenance")
        return self


class _LegacyApplicabilityGoldenCorpus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["2.1"] = "2.1"
    corpus_id: str = "applicability-hard-cases"
    corpus_version: str = "2.1.0"
    cases: tuple[_LegacyApplicabilityGoldenCase, ...]

    @model_validator(mode="after")
    def case_keys_must_be_unique(self) -> _LegacyApplicabilityGoldenCorpus:
        keys = [(case.document_key, case.clause_id) for case in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("legacy applicability golden corpus case keys must be unique")
        return self


class ApplicabilityDetailSeedExpected(BaseModel):
    """Partial historical hint retained for the later detail-enrichment corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_polarity: Literal["included", "excluded"]
    applicability_functions: tuple[Literal["inclusion", "exclusion"], ...] = Field(
        min_length=1,
        max_length=1,
    )
    annotation_scope: Literal["partial"] = "partial"


class ApplicabilityDetailSeedCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: str
    document_key: str
    reference: str
    text: str
    category: str
    expected: ApplicabilityDetailSeedExpected
    provenance: ApplicabilityGoldenProvenance


class ApplicabilityDetailGoldenSeed(BaseModel):
    """Historical labels isolated from the presence-only qualification contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    seed_id: str = "applicability-detail-golden-seed"
    seed_version: str = "1.0.0"
    source_corpus_id: str
    source_corpus_version: str
    source_corpus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: tuple[ApplicabilityDetailSeedCase, ...]

    @model_validator(mode="after")
    def case_keys_must_be_unique(self) -> ApplicabilityDetailGoldenSeed:
        keys = [(case.document_key, case.clause_id) for case in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("applicability detail seed case keys must be unique")
        return self


class ApplicabilityCorpusMigrationResult(BaseModel):
    """Artifacts and accounting from the deterministic schema-2.1 migration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    presence_corpus_path: Path
    detail_seed_path: Path
    migrated_cases: int = Field(ge=0)
    published_cases: int = Field(ge=0)
    detail_seed_cases: int = Field(ge=0)
    positive_cases_without_detail_seed: int = Field(ge=0)


class ApplicabilityCorpusBuildResult(BaseModel):
    """Artifacts and auditable accounting from stratified hard-case selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_path: Path
    review_guide_path: Path
    golden_path: Path
    candidate_count: int = Field(ge=0)
    excluded_existing_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    category_candidate_counts: dict[str, int]
    category_selected_counts: dict[str, int]
    document_count: int = Field(ge=0)
    review_created: bool


class ApplicabilityModelMetrics(BaseModel):
    """Presence diagnostics against published applicability gold cases."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    evaluated_cases: int = Field(ge=0)
    predicted_positive_cases: int = Field(ge=0)
    predicted_positive_rate: float = Field(ge=0.0, le=1.0)
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


class ApplicabilityCaseError(BaseModel):
    """One false presence prediction with enough context for HITL diagnosis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

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

    model_config = ConfigDict(frozen=True, extra="forbid")

    ensemble_id: str
    model_ids: tuple[str, ...]
    metrics: ApplicabilityModelMetrics


class ApplicabilityGoldenRegressionReport(BaseModel):
    """Presence-only calibration report against the applicability golden set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["2.0"] = "2.0"
    golden_corpus_id: str
    golden_corpus_version: str
    prompt_id: str | None = None
    cbox_frame: str | None = None
    published_cases: int = Field(ge=0)
    matched_cases: int = Field(ge=0)
    missing_cases: tuple[str, ...] = ()
    positive_cases: int = Field(ge=0)
    negative_cases: int = Field(ge=0)
    baseline_majority: ApplicabilityModelMetrics
    models: tuple[ApplicabilityModelMetrics, ...]
    ensembles: tuple[ApplicabilityEnsembleMetrics, ...] = ()
    errors: tuple[ApplicabilityCaseError, ...] = ()


STRATIFIED_CATEGORY_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("balanced_presence_disagreement", 45),
    ("minority_presence_disagreement", 35),
    ("framing_sensitive_presence", 20),
)


def build_applicability_golden_review(
    run_archive: Path,
    review_root: Path = Path("local/review"),
    *,
    golden_path: Path | None = None,
    limit: int = 30,
) -> ApplicabilityCorpusBuildResult:
    """Create an incremental deterministic stratified HITL applicability review."""

    report = project_applicability_hard_cases(run_archive)
    candidates = [case for case in report.cases if _review_candidate(case)]
    existing_keys: set[tuple[str, str]] = set()
    if golden_path is not None:
        golden = ApplicabilityGoldenCorpus.load(golden_path)
        existing_keys = {(case.document_key, case.clause_id) for case in golden.cases}
    new_candidates = [
        case for case in candidates if (case.document_key, case.clause_id) not in existing_keys
    ]
    excluded_existing_count = len(candidates) - len(new_candidates)
    selected = _select_stratified_cases(new_candidates, limit=limit)
    if not selected:
        raise ValueError("qualification run contains no new applicability hard-case candidates")

    review_dir = review_root / "applicability" / "3.0.0"
    review_path = review_dir / "applicability-golden-review.csv"
    review_created = False
    if not review_path.exists():
        review_dir.mkdir(parents=True, exist_ok=True)
        _write_review_csv(review_path, selected)
        review_created = True
    review_guide_path = review_dir / "README.md"
    _write_review_guide(review_guide_path)
    return ApplicabilityCorpusBuildResult(
        review_path=review_path,
        review_guide_path=review_guide_path,
        golden_path=review_dir / "applicability-golden-corpus.yaml",
        candidate_count=len(candidates),
        excluded_existing_count=excluded_existing_count,
        selected_count=len(selected),
        category_candidate_counts=dict(
            sorted(Counter(case.category for case in new_candidates).items())
        ),
        category_selected_counts=dict(sorted(Counter(case.category for case in selected).items())),
        document_count=len({case.document_key for case in selected}),
        review_created=review_created,
    )


def _select_stratified_cases(
    candidates: list[PresenceHardCase], *, limit: int
) -> tuple[PresenceHardCase, ...]:
    """Select deterministic category-stratified cases with document round-robin diversity."""

    if limit <= 0 or not candidates:
        return ()
    category_order = tuple(category for category, _ in STRATIFIED_CATEGORY_WEIGHTS)
    grouped = {category: [] for category in category_order}
    for case in candidates:
        if case.category in grouped:
            grouped[case.category].append(case)
    for values in grouped.values():
        values.sort(key=_case_rank)

    quota_limit = min(limit, len(candidates))
    quotas = {
        category: quota_limit * weight // 100 for category, weight in STRATIFIED_CATEGORY_WEIGHTS
    }
    remainder = quota_limit - sum(quotas.values())
    fractional = sorted(
        STRATIFIED_CATEGORY_WEIGHTS,
        key=lambda item: (-(quota_limit * item[1] % 100), category_order.index(item[0])),
    )
    for category, _ in fractional[:remainder]:
        quotas[category] += 1

    selected: list[PresenceHardCase] = []
    selected_keys: set[tuple[str, str]] = set()
    for category in category_order:
        for case in _document_round_robin(grouped[category], quotas[category]):
            selected.append(case)
            selected_keys.add((case.document_key, case.clause_id))

    remaining = quota_limit - len(selected)
    if remaining:
        spill = [
            case
            for category in category_order
            for case in grouped[category]
            if (case.document_key, case.clause_id) not in selected_keys
        ]
        spill.sort(key=_case_rank)
        selected.extend(_document_round_robin(spill, remaining))
    return tuple(selected)


def _document_round_robin(
    cases: list[PresenceHardCase], limit: int
) -> tuple[PresenceHardCase, ...]:
    if limit <= 0:
        return ()
    by_document: dict[str, list[PresenceHardCase]] = defaultdict(list)
    for case in cases:
        by_document[case.document_key].append(case)
    documents = sorted(by_document)
    selected: list[PresenceHardCase] = []
    index = 0
    while len(selected) < limit:
        progressed = False
        for document in documents:
            values = by_document[document]
            if index < len(values):
                selected.append(values[index])
                progressed = True
                if len(selected) == limit:
                    break
        if not progressed:
            break
        index += 1
    return tuple(selected)


def publish_applicability_golden_review(
    review_path: Path,
    run_archive: Path,
    output_path: Path,
    *,
    golden_path: Path | None = None,
) -> ApplicabilityGoldenCorpus:
    """Merge published HITL rows into the presence-only schema-3.0 golden set."""

    with review_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _validate_presence_review_columns(reader.fieldnames)
        rows = list(reader)
    provenance = ApplicabilityGoldenProvenance(
        source_archive=run_archive.name,
        source_archive_sha256=_sha256(run_archive),
    )
    published: list[ApplicabilityGoldenCase] = []
    for row in rows:
        status = (row.get("review_status") or "pending").strip().lower()
        if status != "published":
            continue
        present = _parse_bool(row.get("present"))
        if present is None:
            raise ValueError("published applicability rows require present")
        published.append(
            ApplicabilityGoldenCase(
                clause_id=(row.get("clause_id") or "").strip(),
                document_key=(row.get("document_key") or "").strip(),
                reference=(row.get("reference") or "").strip(),
                text=row.get("text") or "",
                category=(row.get("category") or "minority_presence_disagreement").strip(),
                status="published",
                expected=ApplicabilityGoldenExpected(present=present),
                provenance=provenance,
            )
        )
    if not published:
        raise ValueError("applicability review contains no published cases")

    existing = ApplicabilityGoldenCorpus.load(golden_path) if golden_path is not None else None
    merged = list(existing.cases) if existing is not None else []
    by_key = {(case.document_key, case.clause_id): case for case in merged}
    for case in published:
        key = (case.document_key, case.clause_id)
        prior = by_key.get(key)
        if prior is None:
            merged.append(case)
            by_key[key] = case
            continue
        if prior.expected != case.expected:
            raise ValueError(
                f"conflicting applicability gold label for {case.document_key}/{case.clause_id}"
            )

    merged.sort(key=lambda case: (case.document_key, case.reference, case.clause_id))
    corpus = ApplicabilityGoldenCorpus(cases=tuple(merged))
    _write_yaml(output_path, corpus.model_dump(mode="json"))
    return corpus


def migrate_applicability_golden_corpus(
    source_path: Path,
    output_path: Path,
    detail_seed_path: Path,
) -> ApplicabilityCorpusMigrationResult:
    """Migrate schema 2.1 to presence-only schema 3.0 and isolate historical detail hints."""

    raw = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    legacy = _LegacyApplicabilityGoldenCorpus.model_validate(raw)
    ordered = sorted(
        legacy.cases,
        key=lambda case: (case.document_key, case.reference, case.clause_id),
    )
    presence_cases = tuple(
        ApplicabilityGoldenCase(
            clause_id=case.clause_id,
            document_key=case.document_key,
            reference=case.reference,
            text=case.text,
            category=_presence_category(case.category),
            status=case.status,
            expected=(
                ApplicabilityGoldenExpected(present=case.expected.present)
                if case.expected is not None
                else None
            ),
            provenance=case.provenance,
        )
        for case in ordered
    )
    presence_corpus = ApplicabilityGoldenCorpus(
        corpus_id=legacy.corpus_id,
        cases=presence_cases,
    )

    detail_cases: list[ApplicabilityDetailSeedCase] = []
    positive_without_seed = 0
    for case in ordered:
        expected = case.expected
        if case.status != "published" or expected is None or not expected.present:
            continue
        if expected.polarity is None:
            positive_without_seed += 1
            continue
        if case.provenance is None:
            raise ValueError("published legacy applicability case lacks provenance")
        function = "inclusion" if expected.polarity == "included" else "exclusion"
        detail_cases.append(
            ApplicabilityDetailSeedCase(
                clause_id=case.clause_id,
                document_key=case.document_key,
                reference=case.reference,
                text=case.text,
                category=case.category,
                expected=ApplicabilityDetailSeedExpected(
                    source_polarity=expected.polarity,
                    applicability_functions=(function,),
                ),
                provenance=case.provenance,
            )
        )
    detail_seed = ApplicabilityDetailGoldenSeed(
        source_corpus_id=legacy.corpus_id,
        source_corpus_version=legacy.corpus_version,
        source_corpus_sha256=_sha256(source_path),
        cases=tuple(detail_cases),
    )

    _write_yaml(output_path, presence_corpus.model_dump(mode="json"))
    _write_yaml(detail_seed_path, detail_seed.model_dump(mode="json"))
    return ApplicabilityCorpusMigrationResult(
        presence_corpus_path=output_path,
        detail_seed_path=detail_seed_path,
        migrated_cases=len(presence_cases),
        published_cases=sum(case.status == "published" for case in presence_cases),
        detail_seed_cases=len(detail_cases),
        positive_cases_without_detail_seed=positive_without_seed,
    )


def _presence_category(category: str) -> str:
    """Normalize obsolete detail-oriented strata in the presence-only corpus."""

    if "polarity" in category:
        return "migrated_reviewed_presence"
    return category


def evaluate_applicability_golden_corpus(
    golden: ApplicabilityGoldenCorpus,
    run_archive: Path,
    *,
    prompt_id: str | None = None,
) -> ApplicabilityGoldenRegressionReport:
    """Measure one archived prompt arm against presence-only HITL gold."""

    manifest, snapshot, dataset = _load_run_snapshot(run_archive)
    selected_prompt_id, cbox_frame = _resolve_prompt_frame(snapshot, prompt_id)
    report = _project_run_inputs(
        manifest,
        snapshot,
        dataset,
        prompt_id=selected_prompt_id,
        cbox_frame=cbox_frame,
    )
    return _evaluate_applicability_run_report(
        golden,
        report,
        prompt_id=selected_prompt_id,
        cbox_frame=cbox_frame,
    )


def _evaluate_applicability_run_report(
    golden: ApplicabilityGoldenCorpus,
    report: dict[str, Any],
    *,
    prompt_id: str,
    cbox_frame: str,
) -> ApplicabilityGoldenRegressionReport:
    """Score one already-projected prompt arm against published presence labels."""

    clauses = {
        (str(item.get("document_key")), str(item.get("clause_id"))): item
        for item in report.get("clauses", [])
    }
    published = tuple(
        case for case in golden.cases if case.status == "published" and case.expected is not None
    )
    if not published:
        raise ValueError("applicability golden corpus contains no published cases")

    baseline_predictions: list[tuple[bool, ApplicabilityGoldenExpected]] = []
    model_predictions: dict[str, list[tuple[bool, ApplicabilityGoldenExpected]]] = {}
    case_votes: dict[tuple[str, str], dict[str, bool]] = {}
    matched_cases: list[ApplicabilityGoldenCase] = []
    missing_cases: list[str] = []
    for case in published:
        clause = clauses.get((case.document_key, case.clause_id))
        if clause is None:
            missing_cases.append(f"{case.document_key}/{case.clause_id}")
            continue
        matched_cases.append(case)
        expected = case.expected
        assert expected is not None
        baseline_present = clause.get("applicability_present")
        if baseline_present is not None:
            baseline_predictions.append((bool(baseline_present), expected))
        votes: dict[str, bool] = {}
        for vote in clause.get("votes", []):
            model_id = str(vote.get("model_id"))
            prediction = bool(vote.get("applicability_present"))
            votes[model_id] = prediction
            model_predictions.setdefault(model_id, []).append((prediction, expected))
        case_votes[(case.document_key, case.clause_id)] = votes

    ensemble_specs = _available_ensemble_specs(set(model_predictions))
    ensemble_predictions: dict[str, list[tuple[bool, ApplicabilityGoldenExpected]]] = {
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
            resolved = _offline_majority(tuple(bool(prediction) for prediction in selected))
            if resolved is not None:
                ensemble_predictions[ensemble_id].append((resolved, expected))

    errors: list[ApplicabilityCaseError] = []
    for case in matched_cases:
        expected = case.expected
        assert expected is not None
        clause = clauses[(case.document_key, case.clause_id)]
        votes = case_votes[(case.document_key, case.clause_id)]
        presence_votes = dict(sorted(votes.items()))
        baseline_present = clause.get("applicability_present")
        if baseline_present is not None:
            _append_presence_error(
                errors,
                "baseline_majority",
                case,
                expected,
                bool(baseline_present),
                presence_votes,
            )
        for model_id, predicted_present in sorted(votes.items()):
            _append_presence_error(
                errors,
                model_id,
                case,
                expected,
                predicted_present,
                presence_votes,
            )
        for ensemble_id, model_ids in ensemble_specs:
            selected = [votes.get(model_id) for model_id in model_ids]
            if any(prediction is None for prediction in selected):
                continue
            resolved = _offline_majority(tuple(bool(prediction) for prediction in selected))
            if resolved is not None:
                _append_presence_error(
                    errors,
                    ensemble_id,
                    case,
                    expected,
                    resolved,
                    presence_votes,
                )

    positive_cases = sum(bool(case.expected and case.expected.present) for case in published)
    return ApplicabilityGoldenRegressionReport(
        golden_corpus_id=golden.corpus_id,
        golden_corpus_version=golden.corpus_version,
        prompt_id=prompt_id,
        cbox_frame=cbox_frame,
        published_cases=len(published),
        matched_cases=len(matched_cases),
        missing_cases=tuple(missing_cases),
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


def _offline_majority(predictions: tuple[bool, ...]) -> bool | None:
    present = sum(predictions)
    absent = len(predictions) - present
    if present == absent:
        return None
    return present > absent


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
    predictions: list[tuple[bool, ApplicabilityGoldenExpected]],
) -> ApplicabilityModelMetrics:
    tp = fp = tn = fn = 0
    for predicted_present, expected in predictions:
        if expected.present and predicted_present:
            tp += 1
        elif expected.present:
            fn += 1
        elif predicted_present:
            fp += 1
        else:
            tn += 1
    precision = _ratio(tp, tp + fp, empty=1.0)
    recall = _ratio(tp, tp + fn, empty=1.0)
    specificity = _ratio(tn, tn + fp, empty=1.0)
    total = tp + fp + tn + fn
    predicted_positive = tp + fp
    return ApplicabilityModelMetrics(
        model_id=model_id,
        evaluated_cases=total,
        predicted_positive_cases=predicted_positive,
        predicted_positive_rate=_ratio(predicted_positive, total, empty=0.0),
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
    )


def _load_run_snapshot(
    run_archive: Path,
) -> tuple[dict[str, Any], ApplicabilityPredictionSnapshot, dict[str, Any]]:
    with ZipFile(run_archive) as archive:
        manifest = yaml.safe_load(archive.read("configuration/qualification-manifest.yaml")) or {}
        snapshot_name = _find_member(archive, PREDICTION_SNAPSHOT_FILENAME)
        if snapshot_name is None:
            raise ValueError(
                "qualification run does not contain clause-level applicability predictions; "
                "rerun qualification with the current archive schema"
            )
        snapshot = load_applicability_prediction_snapshot(archive.read(snapshot_name))
        dataset = json.loads(archive.read("inputs/corpus/dataset.json"))
    return manifest, snapshot, dataset


def _available_prompt_frames(
    snapshot: ApplicabilityPredictionSnapshot,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        dict.fromkeys(
            (observation.prompt_id, observation.cbox_frame) for observation in snapshot.observations
        )
    )


def _resolve_prompt_frame(
    snapshot: ApplicabilityPredictionSnapshot,
    prompt_id: str | None,
) -> tuple[str, str]:
    if prompt_id is None:
        return _baseline(snapshot)
    matches = tuple(
        frame for candidate, frame in _available_prompt_frames(snapshot) if candidate == prompt_id
    )
    if not matches:
        available = ", ".join(sorted({item[0] for item in _available_prompt_frames(snapshot)}))
        raise ValueError(
            f"unknown applicability prompt '{prompt_id}'; available prompts: {available}"
        )
    if len(matches) > 1:
        frames = ", ".join(matches)
        raise ValueError(
            f"applicability prompt '{prompt_id}' has multiple CBox frames ({frames}); "
            "prompt ids must identify one archived prompt/frame arm"
        )
    return prompt_id, matches[0]


def _project_run_inputs(
    manifest: dict[str, Any],
    snapshot: ApplicabilityPredictionSnapshot,
    dataset: dict[str, Any],
    *,
    prompt_id: str,
    cbox_frame: str,
) -> dict[str, Any]:
    """Project one archived prompt/frame arm into a presence-only clause/vote view."""

    baseline = _collapsed_predictions(
        snapshot,
        prompt_id=prompt_id,
        cbox_frame=cbox_frame,
        eligible=_presence_eligible_model_ids(manifest),
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
        clauses.append(
            {
                "clause_id": first.clause_id,
                "document_key": first.document_key,
                "reference": reference,
                "clause_text": text,
                "applicability_present": _presence_consensus(tuple(votes.values())),
                "votes": [
                    {
                        "model_id": model_id,
                        "applicability_present": prediction.present,
                    }
                    for model_id, prediction in sorted(votes.items())
                ],
            }
        )
    return {"clauses": clauses}


def _presence_consensus(predictions: tuple[ApplicabilityPrediction, ...]) -> bool | None:
    present = sum(prediction.present for prediction in predictions)
    absent = len(predictions) - present
    if present == absent:
        return None
    return present > absent


def _write_review_csv(path: Path, cases: tuple[PresenceHardCase, ...]) -> None:
    fields = (
        "document_key",
        "reference",
        "category",
        "participating_models",
        "present_count",
        "absent_count",
        "presence_rate",
        "majority_margin",
        "disagreement_score",
        "present_models",
        "absent_models",
        "framing_sensitive_models",
        "selection_rank",
        "text",
        "review_status",
        "present",
        "review_note",
        "clause_id",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rank, case in enumerate(cases, start=1):
            writer.writerow(
                {
                    "document_key": case.document_key,
                    "reference": case.reference,
                    "category": case.category,
                    "participating_models": case.participating_models,
                    "present_count": case.present_count,
                    "absent_count": case.absent_count,
                    "presence_rate": case.presence_rate,
                    "majority_margin": case.majority_margin,
                    "disagreement_score": case.disagreement_score,
                    "present_models": ";".join(case.present_models),
                    "absent_models": ";".join(case.absent_models),
                    "framing_sensitive_models": ";".join(case.framing_sensitive_models),
                    "selection_rank": rank,
                    "text": case.text,
                    "review_status": "pending",
                    "present": "",
                    "review_note": "",
                    "clause_id": case.clause_id,
                }
            )


def _write_review_guide(path: Path) -> None:
    path.write_text(
        "# Applicability Golden Review\n\n"
        "Review the clause text using exactly this question:\n\n"
        "> Does the text contain statements that restrict or extend the applicability of this "
        "clause or a referenced clause?\n\n"
        "Set `present=true` when the answer is yes and `present=false` otherwise. Set "
        "`review_status=published` when the row is complete. Record review observations in "
        "`review_note`; no detail classification is performed in this corpus.\n",
        encoding="utf-8",
    )


def _validate_presence_review_columns(fieldnames: list[str] | None) -> None:
    fields = set(fieldnames or ())
    obsolete = fields.intersection(
        {"polarity", "applicability_polarity", "applicability_function", "applicability_subtype"}
    )
    if obsolete:
        names = ", ".join(sorted(obsolete))
        raise ValueError(
            f"presence-only applicability review must not contain detail columns: {names}"
        )
    required = {
        "document_key",
        "reference",
        "category",
        "text",
        "review_status",
        "present",
        "clause_id",
    }
    missing = required - fields
    if missing:
        raise ValueError(
            "applicability review is missing required columns: " + ", ".join(sorted(missing))
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


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


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
