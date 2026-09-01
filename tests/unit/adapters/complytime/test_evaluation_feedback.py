from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from standards_atlas.adapters.complytime import (
    ComplyTimeGovernanceBundleExporter,
    EvaluationLogFeedbackImporter,
)
from standards_atlas.adapters.gemara.contract import GEMARA_SPEC_VERSION
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    SemanticClassification,
    StandardReference,
    StatementFunction,
    TextBlock,
)


def _clause(
    identifier: str,
    reference: str,
    heading: str,
    *,
    text: str = "",
    parent: str | None = None,
    clause_type: ClauseType = ClauseType.CLAUSE,
    statement_functions: tuple[StatementFunction, ...] = (),
) -> Clause:
    clause = Clause(
        id=ClauseId(value=identifier),
        reference=StandardReference(standard="SAMPLE", year=2026, clause=reference),
        clause_type=clause_type,
        heading=heading,
        parent_id=ClauseId(value=parent) if parent else None,
        content=(TextBlock(id=f"text-{identifier}", text=text),) if text else (),
    )
    if statement_functions:
        clause = clause.with_semantic_classification(
            SemanticClassification(statement_functions=statement_functions)
        )
    return clause


def _document() -> PublicationDocument:
    engineering = EngineeringDocument(
        key=DocumentKey(value="SAMPLE-1"),
        title="Sample Standard - Part 1",
        document_type=DocumentType.STANDARD,
        year=2026,
        version="2026-09",
        clauses=(
            _clause("section-4", "4", "Requirements"),
            _clause(
                "obj-4",
                "4.1",
                "Objective",
                parent="section-4",
                text="The system shall behave deterministically.",
                clause_type=ClauseType.OBJECTIVE,
                statement_functions=(StatementFunction.OBJECTIVE,),
            ),
            _clause(
                "req-4-1",
                "4.1.1",
                "Scheduling",
                parent="obj-4",
                text="Scheduling shall be deterministic.",
                statement_functions=(StatementFunction.REQUIREMENT,),
            ),
        ),
    )
    return PublicationDocument.from_engineering_document(engineering)


def _evaluation_log(*, control_id: str = "obj-4", requirement_id: str = "ar-req-4-1"):
    return {
        "metadata": {
            "id": "evaluation-log-001",
            "type": "EvaluationLog",
            "gemara-version": GEMARA_SPEC_VERSION,
        },
        "result": "Failed",
        "evaluations": [
            {
                "name": "Scheduling control",
                "result": "Failed",
                "message": "One assessment failed.",
                "control": {
                    "reference-id": "sample-1-controls",
                    "entry-id": control_id,
                },
                "assessment-logs": [
                    {
                        "requirement": {
                            "reference-id": "sample-1-controls",
                            "entry-id": requirement_id,
                        },
                        "plan": {
                            "reference-id": "sample-policy",
                            "entry-id": "plan-1",
                        },
                        "description": "Inspect scheduler configuration.",
                        "result": "Failed",
                        "message": "Scheduler is not deterministic.",
                        "applicability": ["all"],
                        "steps": ["Read scheduler configuration"],
                        "steps-executed": 1,
                        "start": "2026-09-01T10:00:00Z",
                        "end": "2026-09-01T10:00:01Z",
                        "recommendation": "Configure deterministic scheduling.",
                    }
                ],
            }
        ],
    }


def _bundle(tmp_path: Path) -> Path:
    path = tmp_path / "bundle"
    ComplyTimeGovernanceBundleExporter().export(_document(), path)
    return path


def _write_log(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "evaluation-log.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_evaluation_feedback_resolves_control_and_requirement_to_clauses(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    log = _write_log(tmp_path, _evaluation_log())
    output = tmp_path / "feedback.json"

    EvaluationLogFeedbackImporter().import_log(log, bundle, output)

    feedback = json.loads(output.read_text(encoding="utf-8"))
    assert feedback["schema_version"] == "1.0"
    assert feedback["document_key"] == "SAMPLE-1"
    assert feedback["evaluation_log_id"] == "evaluation-log-001"
    assert feedback["aggregate_result"] == "Failed"
    assert feedback["evaluation_log_sha256"] == hashlib.sha256(log.read_bytes()).hexdigest()
    assert feedback["summary"]["controls"] == 1
    assert feedback["summary"]["assessments"] == 1
    assert feedback["summary"]["assessment_results"]["Failed"] == 1

    control = feedback["controls"][0]
    assert control["control_id"] == "obj-4"
    assert control["clause_id"] == "obj-4"
    assert control["guidance_catalog_id"] == "sample-1"
    assert control["guidance_entry_id"] == "obj-4"

    assessment = control["assessments"][0]
    assert assessment["assessment_requirement_id"] == "ar-req-4-1"
    assert assessment["clause_id"] == "req-4-1"
    assert assessment["guidance_entry_id"] == "obj-4"
    assert assessment["plan_reference_id"] == "sample-policy"
    assert assessment["plan_entry_id"] == "plan-1"
    assert assessment["result"] == "Failed"


def test_evaluation_feedback_rejects_unknown_assessment_requirement(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    log = _write_log(
        tmp_path,
        _evaluation_log(requirement_id="ar-does-not-exist"),
    )

    with pytest.raises(ValueError, match="unknown assessment requirement"):
        EvaluationLogFeedbackImporter().import_log(log, bundle, tmp_path / "feedback.json")


def test_evaluation_feedback_rejects_wrong_catalog_reference(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    payload = _evaluation_log()
    payload["evaluations"][0]["control"]["reference-id"] = "other-controls"
    log = _write_log(tmp_path, payload)

    with pytest.raises(ValueError, match="expected 'sample-1-controls'"):
        EvaluationLogFeedbackImporter().import_log(log, bundle, tmp_path / "feedback.json")


def test_evaluation_feedback_rejects_modified_bundle_traceability(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    traceability = bundle / "traceability.json"
    traceability.write_text(traceability.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    log = _write_log(tmp_path, _evaluation_log())

    with pytest.raises(ValueError, match="traceability hash mismatch"):
        EvaluationLogFeedbackImporter().import_log(log, bundle, tmp_path / "feedback.json")


def test_evaluation_feedback_rejects_mismatched_gemara_version(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    payload = _evaluation_log()
    payload["metadata"]["gemara-version"] = "0.0.1"
    log = _write_log(tmp_path, payload)

    with pytest.raises(ValueError, match="Gemara version does not match"):
        EvaluationLogFeedbackImporter().import_log(log, bundle, tmp_path / "feedback.json")


def test_evaluation_feedback_is_deterministic(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    log = _write_log(tmp_path, _evaluation_log())
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    importer = EvaluationLogFeedbackImporter()
    importer.import_log(log, bundle, first)
    importer.import_log(log, bundle, second)

    assert first.read_bytes() == second.read_bytes()
