import json
from pathlib import Path

import pytest

from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
    QualificationSelectionClause,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_qualification import (
    SemanticExtractionQualificationConfig,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_run_provenance import (
    semantic_extraction_qualification_provenance,
    validate_semantic_extraction_qualification_provenance,
)


def _selection() -> QualificationRunSelection:
    return QualificationRunSelection(
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="semantic-profile-v1",
        requested_limit=1,
        dataset_sha256="a" * 64,
        corpus_sha256="b" * 64,
        dataset_clause_count=1,
        corpus_clause_count=1,
        selected_clause_count=1,
        clauses=(
            QualificationSelectionClause(example_id="e1", document_key="DOC", clause_id="c1"),
        ),
    )


def _write_cascade(root: Path, *, present: bool) -> None:
    (root / "cascade" / "efficient-local").mkdir(parents=True, exist_ok=True)
    (root / "cascade-provenance.json").write_text(
        json.dumps({"stages": [{"stage_id": "efficient-local"}]}), encoding="utf-8"
    )
    (root / "cascade" / "efficient-local" / "consensus-report.json").write_text(
        json.dumps(
            {
                "clauses": [
                    {
                        "document_key": "DOC",
                        "clause_id": "c1",
                        "applicability_present": present,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_provenance_binds_report_to_current_selection_and_cascade(tmp_path: Path) -> None:
    _write_cascade(tmp_path, present=False)
    selection = _selection()
    config = SemanticExtractionQualificationConfig()
    provenance = semantic_extraction_qualification_provenance(
        run_directory=tmp_path, selection=selection, config=config
    )
    report = {"qualification_input": provenance}

    validate_semantic_extraction_qualification_provenance(
        report, run_directory=tmp_path, selection=selection, config=config
    )

    _write_cascade(tmp_path, present=True)
    with pytest.raises(ValueError, match="does not belong"):
        validate_semantic_extraction_qualification_provenance(
            report, run_directory=tmp_path, selection=selection, config=config
        )


def test_legacy_report_without_provenance_is_rejected(tmp_path: Path) -> None:
    _write_cascade(tmp_path, present=False)
    with pytest.raises(ValueError, match="does not belong"):
        validate_semantic_extraction_qualification_provenance(
            {},
            run_directory=tmp_path,
            selection=_selection(),
            config=SemanticExtractionQualificationConfig(),
        )
