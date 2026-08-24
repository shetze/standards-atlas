"""Focused HITL golden-set support for applicability presence qualification."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Literal
from zipfile import ZipFile

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

_ALLOWED_SUBTYPES = {
    "inclusion",
    "exclusion",
    "exception",
    "applicability_condition",
}


class ApplicabilityGoldenExpected(BaseModel):
    """Human-reviewed applicability reference for one clause."""

    model_config = ConfigDict(frozen=True)

    applicability_present: bool
    applicability_function: str | None = None

    @model_validator(mode="after")
    def subtype_requires_presence(self) -> ApplicabilityGoldenExpected:
        if self.applicability_function is not None:
            if not self.applicability_present:
                raise ValueError("applicability subtype requires applicability_present=true")
            if self.applicability_function not in _ALLOWED_SUBTYPES:
                raise ValueError(
                    f"unsupported applicability subtype: {self.applicability_function}"
                )
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

    schema_version: Literal["1.0"] = "1.0"
    corpus_id: str = "applicability-presence-hard-cases"
    corpus_version: str = "1.0.0"
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
    """Per-model presence accuracy against published applicability gold cases."""

    model_config = ConfigDict(frozen=True)

    model_id: str
    evaluated_cases: int = Field(ge=0)
    presence_accuracy: float = Field(ge=0.0, le=1.0)
    presence_precision: float = Field(ge=0.0, le=1.0)
    presence_recall: float = Field(ge=0.0, le=1.0)
    presence_f1: float = Field(ge=0.0, le=1.0)
    subtype_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)


class ApplicabilityGoldenRegressionReport(BaseModel):
    """Consensus and per-model metrics against the applicability golden set."""

    model_config = ConfigDict(frozen=True)

    published_cases: int = Field(ge=0)
    consensus: ApplicabilityModelMetrics
    models: tuple[ApplicabilityModelMetrics, ...]


def build_applicability_golden_review(
    run_archive: Path,
    review_root: Path = Path("local/review"),
    *,
    limit: int = 30,
) -> ApplicabilityCorpusBuildResult:
    """Create a flat HITL review from final applicability-presence disagreements."""
    report, manifest = _load_run_inputs(run_archive)
    eligibility = {
        str(model.get("id")): bool(
            (model.get("dimension_eligibility") or {}).get("applicability_presence", True)
        )
        for model in manifest.get("models", [])
    }
    cases: list[ApplicabilityGoldenCase] = []
    for clause in report.get("clauses", []):
        votes = [
            vote
            for vote in clause.get("votes", [])
            if eligibility.get(str(vote.get("model_id")), True)
        ]
        presence_values = {bool(vote.get("applicability_present")) for vote in votes}
        if len(presence_values) <= 1:
            continue
        cases.append(
            ApplicabilityGoldenCase(
                clause_id=str(clause["clause_id"]),
                document_key=str(clause["document_key"]),
                reference=_qualified_reference(clause),
                text=str(clause.get("clause_text") or ""),
                category="presence_disagreement",
            )
        )
    cases.sort(key=lambda case: (case.document_key, case.reference, case.clause_id))
    cases = cases[:limit]
    if not cases:
        raise ValueError("qualification run contains no applicability presence disagreements")

    review_dir = review_root / "applicability-presence" / "1.0.0"
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
        present = _parse_bool(row.get("applicability_present"))
        if present is None:
            raise ValueError("published applicability rows require applicability_present")
        subtype = (row.get("applicability_function") or "").strip() or None
        published.append(
            ApplicabilityGoldenCase(
                clause_id=(row.get("clause_id") or "").strip(),
                document_key=(row.get("document_key") or "").strip(),
                reference=(row.get("reference") or "").strip(),
                text=row.get("text") or "",
                category=(row.get("category") or "presence_disagreement").strip(),
                status="published",
                expected=ApplicabilityGoldenExpected(
                    applicability_present=present,
                    applicability_function=subtype,
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
    """Measure final consensus and every available model against HITL gold."""
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

    consensus_predictions: list[tuple[bool, str | None, ApplicabilityGoldenExpected]] = []
    model_predictions: dict[str, list[tuple[bool, str | None, ApplicabilityGoldenExpected]]] = {}
    for case in published:
        clause = clauses.get((case.document_key, case.clause_id))
        if clause is None:
            continue
        expected = case.expected
        assert expected is not None
        consensus_predictions.append(
            (
                bool(clause.get("applicability_present")),
                _first_subtype(clause.get("proposed_applicability_functions")),
                expected,
            )
        )
        for vote in clause.get("votes", []):
            model_id = str(vote.get("model_id"))
            model_predictions.setdefault(model_id, []).append(
                (
                    bool(vote.get("applicability_present")),
                    vote.get("applicability_function"),
                    expected,
                )
            )

    return ApplicabilityGoldenRegressionReport(
        published_cases=len(published),
        consensus=_metrics("consensus", consensus_predictions),
        models=tuple(
            _metrics(model_id, predictions)
            for model_id, predictions in sorted(model_predictions.items())
        ),
    )


def _metrics(
    model_id: str,
    predictions: list[tuple[bool, str | None, ApplicabilityGoldenExpected]],
) -> ApplicabilityModelMetrics:
    tp = fp = tn = fn = 0
    subtype_total = subtype_correct = 0
    for predicted_present, predicted_subtype, expected in predictions:
        if expected.applicability_present and predicted_present:
            tp += 1
        elif expected.applicability_present:
            fn += 1
        elif predicted_present:
            fp += 1
        else:
            tn += 1
        if expected.applicability_present and expected.applicability_function is not None:
            subtype_total += 1
            subtype_correct += predicted_subtype == expected.applicability_function
    precision = _ratio(tp, tp + fp, empty=1.0)
    recall = _ratio(tp, tp + fn, empty=1.0)
    total = tp + fp + tn + fn
    return ApplicabilityModelMetrics(
        model_id=model_id,
        evaluated_cases=total,
        presence_accuracy=_ratio(tp + tn, total, empty=0.0),
        presence_precision=precision,
        presence_recall=recall,
        presence_f1=_f1(precision, recall),
        subtype_accuracy=(subtype_correct / subtype_total if subtype_total else None),
    )


def _load_run_inputs(run_archive: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    with ZipFile(run_archive) as archive:
        report = json.loads(archive.read("reports/consensus-report.json"))
        manifest = yaml.safe_load(archive.read("configuration/qualification-manifest.yaml")) or {}
    return report, manifest


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
        "applicability_present",
        "applicability_function",
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
                    "applicability_present": "",
                    "applicability_function": "",
                    "review_note": "",
                    "clause_id": case.clause_id,
                }
            )


def _write_review_guide(path: Path) -> None:
    path.write_text(
        "# Applicability Golden Review\n\n"
        "Review only the semantic applicability of each clause. Set "
        "`review_status=published` when complete.\n\n"
        "`applicability_present` is `true` only when the clause explicitly changes whether "
        "normative content is in force. Conditions that only change how an activity, method, "
        "analysis, design, calculation, or process is performed are not applicability.\n\n"
        "When presence is true and the subtype is clear, use one of: `inclusion`, `exclusion`, "
        "`exception`, `applicability_condition`. Leave the subtype empty when presence is clear "
        "but the subtype is genuinely uncertain.\n",
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


def _first_subtype(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, tuple) and value:
        return str(value[0])
    return None


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
