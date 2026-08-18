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


def test_analysis_archive_contains_versioned_manifest_and_reports(tmp_path: Path) -> None:
    manifest = tmp_path / "matrix.yaml"
    manifest.write_text("matrix_id: matrix-v1\n", encoding="utf-8")
    report_path = tmp_path / "out" / "matrix-v1" / "report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("{}\n", encoding="utf-8")

    archive = create_analysis_archive(
        output_directory=tmp_path / "out",
        matrix_id="matrix-v1",
        manifest_path=manifest,
        core_paths=(report_path,),
    )

    assert "qualification-analysis-v1.0-standards-atlas-" in archive.name
    with zipfile.ZipFile(archive) as payload:
        names = set(payload.namelist())
        assert "archive-manifest.json" in names
        assert "configuration/qualification-manifest.yaml" in names
        manifest_payload = json.loads(payload.read("archive-manifest.json"))
        assert manifest_payload["schema_version"] == "1.0"
        assert manifest_payload["files"]


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
