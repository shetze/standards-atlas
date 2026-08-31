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
    clauses = (
        ("c1", "This requirement applies to new systems."),
        ("c2", "The analysis shall be performed if requested."),
        ("c3", "This part applies to A but does not apply to B."),
    )
    predictions = {
        "a": ((True, "included"), (False, None), (True, "included")),
        "b": ((False, None), (False, None), (True, "excluded")),
        "c": ((True, "included"), (False, None), (True, "included")),
        "ignored": ((False, None), (False, None), (False, None)),
    }
    snapshot = {
        "schema_version": "1.0",
        "matrix_id": "applicability-test-matrix",
        "observations": [
            {
                "prompt_id": "applicability-clean-full",
                "cbox_frame": "full-context-v1",
                "model_id": model_id,
                "reasoning_mode_id": "disabled",
                "repetition": 1,
                "predictions": [
                    {
                        "clause_key": f"DOC/{clause_id}",
                        "document_key": "DOC",
                        "clause_id": clause_id,
                        "present": values[index][0],
                        "polarity": values[index][1],
                        "confidence": 0.9,
                    }
                    for index, (clause_id, _) in enumerate(clauses)
                ],
            }
            for model_id, values in predictions.items()
        ],
    }
    dataset = {
        "examples": [
            {
                "id": clause_id,
                "input": {
                    "context": {
                        "document_key": "DOC",
                        "clause_id": clause_id,
                        "reference": clause_id[1:],
                    },
                    "content": {"text": text},
                },
            }
            for clause_id, text in clauses
        ]
    }
    manifest = {
        "models": [
            {"id": "a"},
            {"id": "b"},
            {"id": "c"},
            {"id": "ignored", "dimension_eligibility": {"applicability_presence": False}},
        ]
    }
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("configuration/qualification-manifest.yaml", yaml.safe_dump(manifest))
        archive.writestr("inputs/corpus/dataset.json", json.dumps(dataset))
        archive.writestr(
            "applicability-test-matrix/applicability-predictions.json",
            json.dumps(snapshot),
        )
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
    assert metrics["c"].presence_accuracy == 1.0
    assert "ignored" not in metrics


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
