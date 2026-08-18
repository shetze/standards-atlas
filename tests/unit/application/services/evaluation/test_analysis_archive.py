from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from standards_atlas.application.semantic_qualification.analysis_archive import (
    build_analysis_metrics,
    create_analysis_archive,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
    OverallConsensusStatus,
)


def _write_manifest(path: Path) -> None:
    path.write_text(
        "\n".join(
            (
                "manifest_type: qualification_matrix",
                'schema_version: "1.3"',
                "matrix_id: matrix-v1",
                "corpus_id: corpus-v1",
                "task_version: 2.1.0",
                "dataset_version: 2.1.0",
                "prompts:",
                "  - id: content-only",
                "    prompt_version: content-only-v3",
                "models:",
                "  - id: model-one",
                "    provider: ramalama",
                "    model_ref: example/model:Q4_K_M",
            )
        )
        + "\n",
        encoding="utf-8",
    )


def test_analysis_archive_uses_sequential_run_name_and_embedded_metadata(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "matrix.yaml"
    _write_manifest(manifest)
    output_directory = tmp_path / "local" / "evaluation" / "qualification"
    report_path = output_directory / "matrix-v1" / "report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("{}\n", encoding="utf-8")
    metrics = {
        "clause_count": 500,
        "review_count": 25,
        "categories": {"unanimous": 475},
        "dimension_categories": {},
        "overall_statuses": {"resolved": 475},
    }

    archive = create_analysis_archive(
        output_directory=output_directory,
        matrix_id="matrix-v1",
        manifest_path=manifest,
        core_paths=(report_path,),
        analysis_metrics=metrics,
        matrix_passed=False,
        execution_policy={
            "proposal_reuse": False,
            "llm_cache": False,
            "fresh_requested": True,
        },
    )

    assert archive == tmp_path / "local" / "evaluation" / "qualification-run-001.zip"
    with zipfile.ZipFile(archive) as payload:
        names = set(payload.namelist())
        assert "archive-manifest.json" in names
        assert "qualification-run-metadata.json" in names
        assert "configuration/qualification-manifest.yaml" in names
        metadata = json.loads(payload.read("qualification-run-metadata.json"))
        assert metadata["schema_version"] == "1.1"
        assert metadata["archive_id"] == "qualification-run-001"
        assert metadata["sequence_number"] == 1
        assert metadata["qualification_matrix"] == {
            "dataset_version": "2.1.0",
            "id": "matrix-v1",
            "manifest_type": "qualification_matrix",
            "schema_version": "1.3",
            "task_version": "2.1.0",
        }
        assert metadata["corpus"]["id"] == "corpus-v1"
        assert metadata["prompts"] == [{"id": "content-only", "prompt_version": "content-only-v3"}]
        assert metadata["result"]["review_count"] == 25
        assert metadata["result"]["passed"] is False
        assert metadata["execution_policy"] == {
            "fresh_requested": True,
            "llm_cache": False,
            "proposal_reuse": False,
        }
        archive_manifest = json.loads(payload.read("archive-manifest.json"))
        assert archive_manifest["archive_id"] == "qualification-run-001"
        assert archive_manifest["schema_version"] == "1.1"
        assert any(
            item["path"] == "qualification-run-metadata.json" for item in archive_manifest["files"]
        )

    index = json.loads(
        (tmp_path / "local" / "evaluation" / "qualification-run-index.json").read_text()
    )
    assert index["latest"] == 1
    assert index["archives"][0]["file"] == "qualification-run-001.zip"
    assert index["archives"][0]["review_count"] == 25
    assert index["archives"][0]["passed"] is False


def test_analysis_archive_sequence_is_immutable_and_monotonic(tmp_path: Path) -> None:
    manifest = tmp_path / "matrix.yaml"
    _write_manifest(manifest)
    output_directory = tmp_path / "local" / "evaluation" / "qualification"
    report_path = output_directory / "matrix-v1" / "report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("{}\n", encoding="utf-8")

    first = create_analysis_archive(
        output_directory=output_directory,
        matrix_id="matrix-v1",
        manifest_path=manifest,
        core_paths=(report_path,),
    )
    second = create_analysis_archive(
        output_directory=output_directory,
        matrix_id="matrix-v1",
        manifest_path=manifest,
        core_paths=(report_path,),
    )

    assert first.name == "qualification-run-001.zip"
    assert second.name == "qualification-run-002.zip"
    assert first.exists()
    assert second.exists()
    index = json.loads(
        (tmp_path / "local" / "evaluation" / "qualification-run-index.json").read_text()
    )
    assert index["latest"] == 2
    assert [item["sequence_number"] for item in index["archives"]] == [1, 2]


def test_analysis_metrics_separate_observed_and_unresolved_structural_conflicts() -> None:
    clauses = (
        ClauseConsensus(
            clause_id="one",
            document_key="DOC",
            category=ConsensusCategory.UNANIMOUS,
            statement_function_category=ConsensusCategory.UNANIMOUS,
            knowledge_kind_category=ConsensusCategory.UNANIMOUS,
            applicability_category=ConsensusCategory.UNANIMOUS,
            responsibility_category=ConsensusCategory.UNANIMOUS,
            overall_status=OverallConsensusStatus.RESOLVED,
            confidence=1.0,
            participating_models=3,
            requires_review=False,
            applicability_structural_conflict_observed=True,
            applicability_structural_conflict_unresolved=False,
        ),
    )
    report = ConsensusReport(
        matrix_id="matrix-v1",
        corpus_id="corpus-v1",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        generated_at=datetime.now(UTC),
        model_count=3,
        clause_count=1,
        categories={"unanimous": 1},
        review_count=0,
        clauses=clauses,
    )

    metrics = build_analysis_metrics(report=report, cascade_stages=[])

    assert metrics["structural_conflicts"] == {
        "observed": 1,
        "unresolved": 0,
        "resolved_during_cascade": 1,
    }


def test_analysis_metrics_include_non_normative_diagnostics() -> None:
    from standards_atlas.application.semantic_qualification.consensus import ModelVote
    from standards_atlas.domain.model import ApplicabilityFunction

    clauses = (
        ClauseConsensus(
            clause_id="one",
            document_key="DOC",
            reference="1",
            clause_text="This requirement applies to ASIL C and D.",
            category=ConsensusCategory.MAJORITY,
            applicability_category=ConsensusCategory.MAJORITY,
            overall_status=OverallConsensusStatus.REVIEW_REQUIRED,
            applicability_present=True,
            proposed_applicability_functions=(ApplicabilityFunction.INCLUSION,),
            applicability_presence_confidence=2 / 3,
            applicability_subtype_confidence=2 / 3,
            confidence=0.7,
            participating_models=3,
            requires_review=True,
            votes=(
                ModelVote(
                    model_id="model-a",
                    applicability_present=True,
                    applicability_function=ApplicabilityFunction.INCLUSION,
                    repetitions=1,
                    stability=1.0,
                ),
                ModelVote(
                    model_id="model-b",
                    applicability_present=True,
                    applicability_function=ApplicabilityFunction.INCLUSION,
                    repetitions=1,
                    stability=1.0,
                ),
                ModelVote(
                    model_id="model-c",
                    applicability_present=False,
                    repetitions=1,
                    stability=1.0,
                ),
            ),
        ),
    )
    report = ConsensusReport(
        matrix_id="matrix-v1",
        corpus_id="corpus-v1",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        generated_at=datetime.now(UTC),
        model_count=3,
        clause_count=1,
        categories={"majority_consensus": 1},
        review_count=1,
        clauses=clauses,
    )

    metrics = build_analysis_metrics(
        report=report,
        cascade_stages=[
            {
                "stage_id": "efficient-local",
                "entered_clause_count": 1,
                "unresolved_clause_count": 1,
                "entry_reason_counts": {"initial_stage": 1},
                "exit_reason_counts": {"applicability_disagreement": 1},
                "resolution_counts_before": {"applicability": 0},
                "resolution_counts_after": {"applicability": 0},
                "newly_resolved_counts": {"applicability": 0},
            }
        ],
    )

    diagnostics = metrics["diagnostics"]
    assert diagnostics["applicability_conflicts"]["clause_count"] == 1
    assert diagnostics["applicability_conflicts"]["presence_disagreement_count"] == 1
    model_c = next(
        item for item in diagnostics["applicability_model_fitness"] if item["model_id"] == "model-c"
    )
    assert model_c["conflict_none_rate"] == 1.0
    assert diagnostics["stage_contributions"][0]["stage_id"] == "efficient-local"
