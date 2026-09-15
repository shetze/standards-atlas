from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from standards_atlas.application.assertion_qualification import AssertionQualificationReport
from standards_atlas.cli.main import app

runner = CliRunner()


def test_assertion_evaluate_cli_writes_threshold_free_report(tmp_path: Path) -> None:
    golden = tmp_path / "golden.yaml"
    golden.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "id": "dev",
                "version": "1.0.0",
                "partition": "development",
                "ontology_versions": ["standards-atlas-core@2.0.0"],
                "cases": [
                    {
                        "source_document_key": "DOC",
                        "entities": [],
                        "assertions": [],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    proposal = tmp_path / "proposal.json"
    proposal.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "proposal": {
                    "schema_version": 1,
                    "proposal_run_id": "run-1",
                    "source_document_key": "DOC",
                    "ontology_versions": ["standards-atlas-core@2.0.0"],
                    "input_proposals": [],
                    "evidence_anchors": [],
                    "entity_proposals": [],
                    "assertion_proposals": [],
                    "violations": [],
                    "failures": [],
                    "attempts": [],
                    "proposal_provenance": {
                        "extractor": "test",
                        "extractor_version": "1.0.0",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    result = runner.invoke(
        app,
        [
            "evaluation",
            "assertion-evaluate",
            "--golden",
            str(golden),
            "--proposal",
            str(proposal),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Entities" in result.stdout
    assert "Assertions" in result.stdout
    report = AssertionQualificationReport.model_validate_json(output.read_text(encoding="utf-8"))
    assert report.golden_suite_id == "dev"
    assert report.aggregate.entities.f1 == 1.0
    assert "passed" not in AssertionQualificationReport.model_fields
    assert "accepted" not in AssertionQualificationReport.model_fields


def test_assertion_evaluate_help_is_registered() -> None:
    result = runner.invoke(app, ["evaluation", "assertion-evaluate", "--help"])
    assert result.exit_code == 0
    assert "--golden" in result.stdout
    assert "--proposal" in result.stdout
    assert "--output" in result.stdout
