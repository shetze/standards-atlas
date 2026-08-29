"""Run-input provenance for semantic extraction qualification reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_qualification import (
    SemanticExtractionQualificationConfig,
)


def semantic_extraction_qualification_provenance(
    *,
    run_directory: Path,
    selection: QualificationRunSelection,
    config: SemanticExtractionQualificationConfig,
) -> dict[str, str]:
    """Fingerprint every run input that determines semantic extraction qualification."""
    return {
        "selection_sha256": _canonical_sha256(selection.model_dump(mode="json")),
        "dataset_sha256": selection.dataset_sha256,
        "corpus_sha256": selection.corpus_sha256,
        "semantic_extraction_config_sha256": _canonical_sha256(config.model_dump(mode="json")),
        "cascade_context_sha256": _cascade_context_sha256(run_directory),
    }


def validate_semantic_extraction_qualification_provenance(
    report: dict[str, Any],
    *,
    run_directory: Path,
    selection: QualificationRunSelection,
    config: SemanticExtractionQualificationConfig,
) -> None:
    """Reject a report that was not produced from the current qualification inputs."""
    actual = report.get("qualification_input")
    expected = semantic_extraction_qualification_provenance(
        run_directory=run_directory,
        selection=selection,
        config=config,
    )
    if actual != expected:
        raise ValueError(
            "semantic extraction qualification report does not belong to the current "
            "qualification inputs"
        )


def _cascade_context_sha256(run_directory: Path) -> str:
    provenance_path = run_directory / "cascade-provenance.json"
    members: list[dict[str, Any]] = []
    if provenance_path.is_file():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        members.append({"path": "cascade-provenance.json", "payload": provenance})
        for stage in provenance.get("stages", []):
            if not isinstance(stage, dict) or not stage.get("stage_id"):
                continue
            stage_id = str(stage["stage_id"])
            report_path = run_directory / "cascade" / stage_id / "consensus-report.json"
            if report_path.is_file():
                members.append(
                    {
                        "path": f"cascade/{stage_id}/consensus-report.json",
                        "payload": json.loads(report_path.read_text(encoding="utf-8")),
                    }
                )
    return _canonical_sha256(members)


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
