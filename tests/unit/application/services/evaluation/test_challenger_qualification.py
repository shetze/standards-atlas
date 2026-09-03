from pathlib import Path

import pytest

from standards_atlas.application.semantic_qualification.challenger import (
    build_challenger_manifest,
    write_challenger_comparison,
    write_challenger_manifest,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)

MANIFEST = Path("manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml")


def test_challenger_manifest_reuses_contract_without_mutating_cascade(tmp_path: Path) -> None:
    source = QualificationMatrixManifest.load(MANIFEST)
    derived = build_challenger_manifest(source)

    assert source.execution.mode == "cascade"
    assert derived.execution.mode == "full_matrix"
    assert derived.matrix_id == f"{source.matrix_id}-challengers"
    assert {model.id for model in derived.models} == set(source.challenger_qualification.model_ids)
    assert [model.id for model in derived.models[:3]] == [
        "qwen3-8b-q4-k-m",
        "smollm3-3b-q4-k-m",
        "phi-4-14b-q4-k-m",
    ]
    assert derived.observations == ()
    assert derived.review_imports == ()

    path = write_challenger_manifest(manifest=source, path=tmp_path / "challenger.yaml")
    reloaded = QualificationMatrixManifest.load(path)
    assert reloaded.consensus.output_directory == tmp_path / "consensus"


def test_challenger_manifest_validates_unknown_model() -> None:
    source = QualificationMatrixManifest.load(MANIFEST)
    payload = source.model_dump(mode="python")
    payload["challenger_qualification"]["groups"][0]["challengers"] = ("missing",)

    with pytest.raises(ValueError, match="unknown models in challenger group"):
        QualificationMatrixManifest.model_validate(payload)


def test_v4_prompts_define_normalized_confidence_contract() -> None:
    prompt_root = Path(
        "src/standards_atlas/resources/semantic/prompts/statement-function-classification"
    )
    prompt_names = (
        "content-only-v4",
        "structure-aware-v4",
        "evidence-first-v4",
        "bounded-reasoning-v4",
    )

    for prompt_name in prompt_names:
        system_prompt = (prompt_root / prompt_name / "system.txt").read_text(encoding="utf-8")
        assert "Confidence values MUST be JSON numbers from 0.0 through 1.0." in system_prompt
        assert "Use 0.95 for ninety-five percent confidence" in system_prompt
        assert 'never use 95, 95.0, or "95%"' in system_prompt


def test_challenger_comparison_ignores_ineligible_candidates(tmp_path: Path) -> None:
    source = QualificationMatrixManifest.load(MANIFEST)
    metrics = {
        "diagnostics": {
            "applicability_model_fitness": [
                {
                    "model_id": "smollm3-3b-q4-k-m",
                    "vote_count": 4,
                    "present_count": 1,
                    "absent_count": 3,
                    "absent_rate": 0.75,
                    "conflict_vote_count": 2,
                    "conflict_absent_count": 2,
                    "conflict_absent_rate": 1.0,
                    "presence_reference_agreement_rate": 0.5,
                }
            ]
        }
    }
    matrix = {
        "candidates": [
            {
                "model_id": "smollm3-3b-q4-k-m",
                "qualification_eligible": True,
                "mean_prediction_success_rate": 1.0,
                "mean_duration_seconds": 10.0,
            },
            {
                "model_id": "smollm3-3b-q4-k-m",
                "qualification_eligible": False,
                "mean_prediction_success_rate": 0.0,
                "mean_duration_seconds": None,
            },
        ]
    }
    import json

    (tmp_path / "qualification-analysis-metrics.json").write_text(
        json.dumps(metrics), encoding="utf-8"
    )
    (tmp_path / "qualification-matrix.json").write_text(json.dumps(matrix), encoding="utf-8")

    json_path, markdown_path = write_challenger_comparison(
        source_manifest=source, run_directory=tmp_path
    )
    comparison = json.loads(json_path.read_text(encoding="utf-8"))
    efficient = next(group for group in comparison["groups"] if group["id"] == "efficient-local")
    aya = next(model for model in efficient["models"] if model["model_id"] == "smollm3-3b-q4-k-m")

    assert aya["mean_prediction_success_rate"] == 1.0
    assert aya["mean_duration_seconds"] == 10.0
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Presence votes" in markdown
    assert "Conflict absent rate" in markdown
    assert "Subtype agreement" not in markdown


def test_loads_applicability_hard_cases_from_qualification_archive(tmp_path: Path) -> None:
    import json
    from zipfile import ZipFile

    from standards_atlas.application.semantic_qualification.challenger import (
        load_hard_case_selection,
    )

    source = QualificationMatrixManifest.load(MANIFEST)
    archive_path = tmp_path / "qualification-run.zip"
    metadata = {
        "corpus": {
            "id": source.corpus_id,
            "dataset_version": source.dataset_version,
        },
        "qualification_matrix": {"id": source.matrix_id},
    }
    clauses = [
        {
            "clause_id": "presence-conflict",
            "votes": [
                {"applicability_present": True, "applicability_function": "inclusion"},
                {"applicability_present": False, "applicability_function": None},
            ],
        },
        {
            "clause_id": "ineligible-presence-conflict",
            "votes": [
                {
                    "applicability_present": True,
                    "applicability_presence_eligible": True,
                },
                {
                    "applicability_present": False,
                    "applicability_presence_eligible": False,
                },
            ],
        },
        {
            "clause_id": "stable",
            "votes": [
                {"applicability_present": True, "applicability_function": "inclusion"},
                {"applicability_present": True, "applicability_function": "inclusion"},
            ],
        },
    ]
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("qualification-run-metadata.json", json.dumps(metadata))
        archive.writestr(
            f"../../consensus/{source.matrix_id}/consensus-report.json",
            json.dumps({"clauses": clauses}),
        )

    clause_ids, selection = load_hard_case_selection(
        source_manifest=source,
        run_archive=archive_path,
        sample="applicability-conflicts",
    )

    assert clause_ids == ("presence-conflict",)
    assert selection["clause_count"] == 1
    assert selection["sample"] == "applicability-conflicts"
    assert selection["source_matrix_id"] == source.matrix_id


def test_hard_case_archive_must_match_dataset_version(tmp_path: Path) -> None:
    import json
    from zipfile import ZipFile

    from standards_atlas.application.semantic_qualification.challenger import (
        load_hard_case_selection,
    )

    source = QualificationMatrixManifest.load(MANIFEST)
    archive_path = tmp_path / "qualification-run.zip"
    metadata = {
        "corpus": {"id": source.corpus_id, "dataset_version": "different"},
        "qualification_matrix": {"id": source.matrix_id},
    }
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("qualification-run-metadata.json", json.dumps(metadata))

    with pytest.raises(ValueError, match="dataset version does not match"):
        load_hard_case_selection(
            source_manifest=source,
            run_archive=archive_path,
            sample="applicability-conflicts",
        )
