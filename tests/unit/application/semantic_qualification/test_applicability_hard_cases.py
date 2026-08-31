from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import yaml

from standards_atlas.application.semantic_qualification.applicability_hard_cases import (
    PREDICTION_SNAPSHOT_FILENAME,
    ApplicabilityPrediction,
    ApplicabilityPredictionObservation,
    ApplicabilityPredictionSnapshot,
    analyze_applicability_hard_cases,
    persist_applicability_prediction_snapshot,
)


def _prediction(model_clause: str, present: bool, polarity: str | None = None):
    return ApplicabilityPrediction(
        clause_key=f"functional-safety:DOC:{model_clause}",
        document_key="DOC",
        clause_id=model_clause,
        present=present,
        polarity=polarity,
        confidence=0.8,
    )


def _archive(path: Path) -> Path:
    observations = []
    full = {
        "a": {"c1": True, "c2": False, "c3": True},
        "b": {"c1": True, "c2": False, "c3": True},
        "c": {"c1": False, "c2": False, "c3": True},
        "d": {"c1": False, "c2": False, "c3": True},
    }
    minimal = {
        "a": {"c1": False, "c2": False, "c3": True},
        "b": {"c1": True, "c2": False, "c3": True},
        "c": {"c1": False, "c2": False, "c3": True},
        "d": {"c1": False, "c2": False, "c3": True},
    }
    for prompt, frame, values in (
        ("applicability-clean-full", "full-context-v1", full),
        ("applicability-clean-minimal", "applicability-minimal-v1", minimal),
    ):
        for model, clauses in values.items():
            observations.append(
                ApplicabilityPredictionObservation(
                    prompt_id=prompt,
                    cbox_frame=frame,
                    model_id=model,
                    reasoning_mode_id="disabled",
                    repetition=1,
                    predictions=tuple(
                        _prediction(
                            clause_id,
                            present,
                            "included" if present else None,
                        )
                        for clause_id, present in clauses.items()
                    ),
                )
            )
    snapshot = ApplicabilityPredictionSnapshot(matrix_id="matrix", observations=tuple(observations))
    manifest = {"models": [{"id": model} for model in full]}
    dataset = {
        "examples": [
            {
                "id": clause_id,
                "input": {
                    "content": {"text": f"Clause {clause_id}"},
                    "context": {
                        "document_key": "DOC",
                        "clause_id": clause_id,
                        "reference": index,
                    },
                },
            }
            for index, clause_id in enumerate(("c1", "c2", "c3"), start=1)
        ]
    }
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("configuration/qualification-manifest.yaml", yaml.safe_dump(manifest))
        archive.writestr("inputs/corpus/dataset.json", json.dumps(dataset))
        archive.writestr(f"matrix/{PREDICTION_SNAPSHOT_FILENAME}", snapshot.model_dump_json())
    return path


def test_analyze_applicability_hard_cases_ranks_balanced_disagreement(tmp_path: Path) -> None:
    report, artifacts = analyze_applicability_hard_cases(
        _archive(tmp_path / "qualification-run.zip"), tmp_path / "out", limit=10
    )

    assert report.analyzed_clauses == 3
    assert report.cases[0].clause_id == "c1"
    assert report.cases[0].category == "balanced_presence_disagreement"
    assert report.cases[0].present_count == 2
    assert report.cases[0].absent_count == 2
    assert report.cases[0].disagreement_score == 1.0
    assert report.cases[0].framing_sensitive_models == ("a",)
    assert report.category_counts["unanimous_absent"] == 1
    assert report.category_counts["unanimous_present"] == 1
    assert artifacts.selected_count == 1
    with artifacts.review_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["vote_summary"] == "2 present / 2 absent"
    assert rows[0]["reference"] == "DOC:1"


def test_hard_case_analysis_requires_archived_clause_predictions(tmp_path: Path) -> None:
    archive_path = tmp_path / "qualification-run.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("configuration/qualification-manifest.yaml", "models: []\n")
        archive.writestr("inputs/corpus/dataset.json", '{"examples": []}')
    try:
        analyze_applicability_hard_cases(archive_path, tmp_path / "out")
    except ValueError as exc:
        assert "clause-level applicability predictions" in str(exc)
    else:
        raise AssertionError("missing prediction snapshot must fail")


def test_persist_prediction_snapshot_projects_only_applicability_fields(tmp_path: Path) -> None:
    run = tmp_path / "run" / "c1"
    run.mkdir(parents=True)
    payload = {
        "annotation_candidate": {
            "schema_version": "1.0",
            "task": "semantic-profile-classification",
            "lifecycle_status": "proposed",
            "clause": {
                "knowledge_domain": "functional-safety",
                "document_key": "DOC",
                "clause_id": "c1",
                "content_hash": "sha256:" + "a" * 64,
            },
            "proposal": {
                "applicability_present": True,
                "applicability_functions": ["inclusion"],
                "primary_applicability_function": "inclusion",
                "confidence": 0.91,
            },
            "generator": {
                "provider": "test",
                "model": "model-a",
                "prompt_id": "applicability-clean-full",
                "generated_at": "2026-08-31T00:00:00Z",
            },
        }
    }
    (run / "evaluation.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    manifest = SimpleNamespace(
        matrix_id="matrix",
        prompts=(SimpleNamespace(id="applicability-clean-full", cbox_frame="full-context-v1"),),
        observations=(
            SimpleNamespace(
                prompt_id="applicability-clean-full",
                model_id="model-a",
                reasoning_mode_id="disabled",
                repetition=1,
                run_directory=tmp_path / "run",
            ),
        ),
    )
    path = persist_applicability_prediction_snapshot(manifest, tmp_path / "out")
    snapshot = ApplicabilityPredictionSnapshot.model_validate_json(path.read_text())
    prediction = snapshot.observations[0].predictions[0]
    assert prediction.present is True
    assert prediction.polarity == "included"
    assert prediction.confidence == 0.91
