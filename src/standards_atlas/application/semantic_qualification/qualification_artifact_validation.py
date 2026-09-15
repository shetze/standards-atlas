"""Validate recognized qualification contracts without migrating recorded bytes.

This is not a schema detector for arbitrary JSON. Direct callers with custom
filenames must validate through their family's model/reader as usual.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath

import yaml

from standards_atlas.application.model.context_adoption import ContextAdoptionBatch
from standards_atlas.application.semantic_qualification.cascade_provenance import (
    validate_cascade_provenance,
)
from standards_atlas.application.semantic_qualification.consensus import ConsensusReport
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
    QualificationMatrixReport,
)

QUALIFICATION_ARTIFACT_NAMES = frozenset(
    {
        "consensus-report.json",
        "final-consensus-report.json",
        "known-gate-consensus.json",
        "qualification-matrix.json",
        "cascade-provenance.json",
        "context-adoption-batch.json",
        "qualification-manifest.yaml",
    }
)


def validate_qualification_artifact(name: str, raw: bytes) -> None:
    """Reject obsolete embedded inputs; preserve missing/explicit observation keys."""
    filename = PurePosixPath(name).name
    try:
        if filename in {
            "consensus-report.json",
            "final-consensus-report.json",
            "known-gate-consensus.json",
        }:
            ConsensusReport.model_validate_json(raw)
        elif filename == "qualification-matrix.json":
            QualificationMatrixReport.model_validate_json(raw)
        elif filename == "cascade-provenance.json":
            validate_cascade_provenance(json.loads(raw))
        elif filename == "context-adoption-batch.json":
            ContextAdoptionBatch.model_validate_json(raw)
        elif filename == "qualification-manifest.yaml":
            QualificationMatrixManifest.model_validate(yaml.safe_load(raw))
    except ValueError as exc:
        raise ValueError(f"invalid qualification artifact {name}: {exc}") from exc
