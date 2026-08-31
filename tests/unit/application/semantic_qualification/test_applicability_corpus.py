from __future__ import annotations

import csv
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import yaml
from pydantic import ValidationError

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
    ApplicabilityGoldenExpected,
    build_applicability_golden_review,
    evaluate_applicability_golden_corpus,
    publish_applicability_golden_review,
)


def _run_archive(path: Path) -> Path:
    report = {
        "clauses": [
            {
                "clause_id": "c1",
                "document_key": "DOC",
                "reference": "DOC:1",
                "clause_text": "This requirement applies to new systems.",
                "applicability_present": True,
                "applicability_polarity": "included",
                "votes": [
                    {
                        "model_id": "a",
                        "applicability_present": True,
                        "applicability_polarity": "included",
                    },
                    {
                        "model_id": "b",
                        "applicability_present": False,
                        "applicability_polarity": None,
                    },
                    {
                        "model_id": "ignored",
                        "applicability_present": False,
                        "applicability_polarity": None,
                    },
                ],
            },
            {
                "clause_id": "c2",
                "document_key": "DOC",
                "reference": "DOC:2",
                "clause_text": "The analysis shall be performed if requested.",
                "applicability_present": False,
                "applicability_polarity": None,
                "votes": [
                    {
                        "model_id": "a",
                        "applicability_present": False,
                        "applicability_polarity": None,
                    },
                    {
                        "model_id": "b",
                        "applicability_present": False,
                        "applicability_polarity": None,
                    },
                ],
            },
            {
                "clause_id": "c3",
                "document_key": "DOC",
                "reference": "DOC:3",
                "clause_text": "This part applies to A but does not apply to B.",
                "applicability_present": True,
                "applicability_polarity": "included",
                "votes": [
                    {
                        "model_id": "a",
                        "applicability_present": True,
                        "applicability_polarity": "included",
                    },
                    {
                        "model_id": "b",
                        "applicability_present": True,
                        "applicability_polarity": "excluded",
                    },
                ],
            },
        ]
    }
    manifest = {
        "models": [
            {"id": "a"},
            {"id": "b"},
            {"id": "ignored", "dimension_eligibility": {"applicability_presence": False}},
        ]
    }
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("reports/consensus-report.json", json.dumps(report))
        archive.writestr("configuration/qualification-manifest.yaml", yaml.safe_dump(manifest))
    return path


def test_build_publish_and_evaluate_applicability_hard_cases(tmp_path: Path) -> None:
    archive = _run_archive(tmp_path / "qualification-run.zip")
    result = build_applicability_golden_review(archive, tmp_path / "review")
    assert result.selected_count == 2
    with result.review_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["reference"] == "DOC:1"
    assert rows[0]["category"] == "presence_disagreement"
    assert rows[1]["reference"] == "DOC:3"
    assert rows[1]["category"] == "polarity_disagreement"
    rows[0]["review_status"] = "published"
    rows[0]["present"] = "true"
    rows[0]["polarity"] = "included"
    with result.review_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    golden = publish_applicability_golden_review(result.review_path, archive, result.golden_path)
    assert len(golden.cases) == 1
    loaded = ApplicabilityGoldenCorpus.load(result.golden_path)
    report = evaluate_applicability_golden_corpus(loaded, archive)
    assert report.consensus.presence_accuracy == 1.0
    metrics = {item.model_id: item for item in report.models}
    assert metrics["a"].presence_accuracy == 1.0
    assert metrics["b"].presence_accuracy == 0.0


def test_applicability_golden_contract_rejects_legacy_subtype_fields() -> None:
    with pytest.raises(ValidationError):
        ApplicabilityGoldenExpected.model_validate(
            {"present": True, "applicability_polarity": "included"}
        )


def test_applicability_golden_contract_accepts_only_binary_polarity() -> None:
    included = ApplicabilityGoldenExpected(present=True, polarity="included")
    excluded = ApplicabilityGoldenExpected(present=True, polarity="excluded")
    assert included.polarity is not None and included.polarity.value == "included"
    assert excluded.polarity is not None and excluded.polarity.value == "excluded"
    with pytest.raises(ValidationError):
        ApplicabilityGoldenExpected(present=True, polarity="exception")
    with pytest.raises(ValidationError):
        ApplicabilityGoldenExpected(present=True, polarity="applicability_condition")
    with pytest.raises(ValidationError):
        ApplicabilityGoldenExpected(present=False, polarity="included")
