from __future__ import annotations

import json
import zipfile
from pathlib import Path

from standards_atlas.application.semantic_qualification.analysis_archive import (
    create_analysis_archive,
)
from standards_atlas.application.semantic_qualification.qualification_suite_archive import (
    create_qualification_suite_archive,
    next_qualification_suite_run_id,
    qualification_archives_for_suite,
)
from standards_atlas.shared.hashing import sha256_file


def _matrix_manifest(path: Path, matrix_id: str, task: str) -> None:
    path.write_text(
        "\n".join(
            (
                "manifest_type: qualification_matrix",
                'schema_version: "1.6"',
                f"matrix_id: {matrix_id}",
                "corpus_id: corpus-v1",
                f"task: {task}",
                "task_version: 1.0.0",
                "dataset_version: 1.0.0",
            )
        )
        + "\n",
        encoding="utf-8",
    )


def test_suite_archive_correlates_task_runs_and_hashes(tmp_path: Path) -> None:
    archive_dir = tmp_path / "local" / "evaluation"
    output = tmp_path / ".atlas" / "qualification"
    suite = tmp_path / "suite.yaml"
    suite.write_text(
        "manifest_type: qualification_suite\n"
        "schema_version: 1\n"
        "suite_id: routed-v4\n"
        "version: 1.0.0\n"
        "routing_manifest: routing.yaml\n"
        "qualification_manifests:\n"
        "  - a.yaml\n"
        "  - b.yaml\n",
        encoding="utf-8",
    )
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        "manifest_type: routing_contract\nschema_version: 1\n"
        "contract:\n  id: contract\n  version: 1.1.0\n",
        encoding="utf-8",
    )
    suite_run_id = next_qualification_suite_run_id(archive_dir)
    assert suite_run_id == "qualification-suite-run-001"

    run_paths = []
    for index, task in enumerate(("task-a", "task-b"), start=1):
        manifest = tmp_path / f"matrix-{index}.yaml"
        _matrix_manifest(manifest, f"matrix-{index}", task)
        report = output / f"matrix-{index}" / "report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("{}\n", encoding="utf-8")
        run_paths.append(
            create_analysis_archive(
                output_directory=output,
                matrix_id=f"matrix-{index}",
                manifest_path=manifest,
                core_paths=(report,),
                archive_directory=archive_dir,
                suite_run_id=suite_run_id,
                routing_metadata={
                    "task": task,
                    "contract_id": "contract",
                    "contract_version": "1.1.0",
                    "aggregate": {
                        "admitted": index,
                        "skipped": 10 - index,
                        "dispositions": {"required": index},
                    },
                },
            )
        )

    correlated = qualification_archives_for_suite(archive_dir, suite_run_id)
    assert correlated == tuple(run_paths)
    suite_archive = create_qualification_suite_archive(
        archive_directory=archive_dir,
        suite_run_id=suite_run_id,
        suite_manifest_path=suite,
        routing_manifest_path=routing,
        qualification_archives=correlated,
    )

    with zipfile.ZipFile(suite_archive) as payload:
        metadata = json.loads(payload.read("qualification-suite-run-metadata.json"))
        manifest = json.loads(payload.read("archive-manifest.json"))
        assert metadata["suite_run_id"] == suite_run_id
        assert metadata["routing_contract"] == {
            "id": "contract",
            "manifest_sha256": sha256_file(routing),
            "version": "1.1.0",
        }
        assert len(metadata["qualification_runs"]) == 2
        assert metadata["routing_aggregates"]["task-a"]["admitted"] == 1
        assert metadata["routing_aggregates"]["task-b"]["skipped"] == 8
        assert {item["sha256"] for item in manifest["qualification_runs"]} == {
            sha256_file(path) for path in run_paths
        }
        assert "configuration/qualification-suite-manifest.yaml" in payload.namelist()
        assert "configuration/routing-manifest.yaml" in payload.namelist()
