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
                "audit": {"review_id": "test", "review_version": "1", "audit_sha256": "a" * 64},
                "ontology_versions": ["standards-atlas-core@2.0.0"],
                "cases": [
                    {
                        "source_document_key": "DOC",
                        "clause_id": {"value": "c1"},
                        "reference": "DOC:1",
                        "canonical_reference": "DOC 1",
                        "text_sha256": "b" * 64,
                        "source_sha256": "c" * 64,
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
    assert report.aggregate.entities.f1.value is None
    assert report.aggregate.entities.f1.status.value == "not_applicable"
    assert "passed" not in AssertionQualificationReport.model_fields
    assert "accepted" not in AssertionQualificationReport.model_fields


def test_assertion_evaluate_help_is_registered() -> None:
    result = runner.invoke(app, ["evaluation", "assertion-evaluate", "--help"])
    assert result.exit_code == 0
    assert "--golden" in result.stdout
    assert "--proposal" in result.stdout
    assert "--output" in result.stdout
    assert "--summary-output" in result.stdout
    assert "--source-package-workspace" in result.stdout


def test_assertion_cascade_help_is_registered() -> None:
    result = runner.invoke(app, ["evaluation", "assertion-cascade", "--help"])
    assert result.exit_code == 0
    assert "--document-key" in result.stdout
    assert "--efficient-model" in result.stdout
    assert "--verifier-model" in result.stdout
    assert "--escalation-model" in result.stdout
    assert "--ontology-version" in result.stdout


def test_assertion_auto_adoption_help_is_registered() -> None:
    result = runner.invoke(app, ["evaluation", "assertion-auto-adoption", "--help"])
    assert result.exit_code == 0
    assert "--policy" in result.stdout
    assert "--development-golden" in result.stdout
    assert "--development-report" in result.stdout
    assert "--holdout-golden" in result.stdout
    assert "--holdout-report" in result.stdout
    assert "--cascade-report" in result.stdout
    assert "--efficient-proposal" in result.stdout
    assert "--escalation-proposal" in result.stdout
    assert "--output" in result.stdout


def test_assertion_review_pilot_help_is_registered() -> None:
    build = runner.invoke(app, ["evaluation", "assertion-review-pilot-build", "--help"])
    assert build.exit_code == 0
    assert "--source" in build.stdout
    assert "--ontology-version" in build.stdout
    assert "--clause-id" in build.stdout

    attach = runner.invoke(app, ["evaluation", "assertion-review-pilot-attach", "--help"])
    assert attach.exit_code == 0
    assert "--cascade-report" in attach.stdout
    assert "--efficient-proposal" in attach.stdout

    publish = runner.invoke(app, ["evaluation", "assertion-review-pilot-publish", "--help"])
    assert publish.exit_code == 0
    assert "--review" in publish.stdout
    assert "--output" in publish.stdout


def test_assertion_cascade_help_exposes_review_pilot_selection() -> None:
    result = runner.invoke(app, ["evaluation", "assertion-cascade", "--help"])
    assert result.exit_code == 0
    assert "--review-pilot" in result.stdout


def test_assertion_evaluate_cli_loads_native_private_source_packages(tmp_path: Path) -> None:
    import hashlib

    from standards_atlas.adapters.filesystem import (
        FileSystemContextSourcePackageRepository,
        FileSystemDocumentKnowledgeProposalRepository,
    )
    from standards_atlas.application.context import (
        build_context_source_package,
        build_structured_context_candidates,
        select_structured_context,
    )
    from standards_atlas.domain.model import (
        CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT,
        Clause,
        ClauseId,
        ClauseType,
        DocumentKey,
        DocumentKnowledgeProposal,
        DocumentType,
        EngineeringDocument,
        KnowledgeProposalProvenance,
        StandardReference,
        TextBlock,
    )

    text = "Synthetic source body"
    clause = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="DOC", clause="1"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="text", text=text),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Synthetic",
        document_type=DocumentType.OTHER,
        clauses=(clause,),
    )
    inventory = build_structured_context_candidates(document, clause)
    selection = select_structured_context(inventory)
    package = build_context_source_package(document, inventory, selection)
    package_binding = FileSystemContextSourcePackageRepository(tmp_path).save(package)
    proposal = DocumentKnowledgeProposal(
        proposal_run_id="run-native-package",
        source_document_key="DOC",
        ontology_versions=("standards-atlas-core@2.0.0",),
        context_source_bindings=(package_binding,),
        proposal_provenance=KnowledgeProposalProvenance(
            extractor="synthetic-test",
            extractor_version="1",
            source_binding_contract_id=CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT,
        ),
    )
    proposal_repository = FileSystemDocumentKnowledgeProposalRepository(tmp_path)
    proposal_repository.save(proposal)
    proposal_path = tmp_path / "knowledge-proposals" / proposal.proposal_run_id / "DOC.json"

    golden = tmp_path / "golden-native.yaml"
    golden.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "id": "dev-native",
                "version": "1",
                "partition": "development",
                "audit": {"review_id": "test", "review_version": "1", "audit_sha256": "a" * 64},
                "ontology_versions": ["standards-atlas-core@2.0.0"],
                "cases": [
                    {
                        "source_document_key": "DOC",
                        "clause_id": {"value": "c1"},
                        "reference": "DOC:1",
                        "canonical_reference": "DOC 1",
                        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "source_sha256": "c" * 64,
                        "entities": [],
                        "assertions": [],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "native-report.json"

    result = runner.invoke(
        app,
        [
            "evaluation",
            "assertion-evaluate",
            "--golden",
            str(golden),
            "--proposal",
            str(proposal_path),
            "--source-package-workspace",
            str(tmp_path),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    report = AssertionQualificationReport.model_validate_json(output.read_text())
    assert report.source_binding == "native_package_verified"
    assert report.cases[0].source_comparison.status.value == "matching"


def test_ap03_preflight_cli_is_model_free_and_text_free(tmp_path: Path) -> None:
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "llm.yaml").write_bytes(Path("cfg/llm.yaml").read_bytes())
    (tmp_path / "manifests").mkdir()

    result = runner.invoke(
        app,
        ["evaluation", "assertion-ap03-preflight", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["contract_id"] == "ap03-qualification-preflight-v1"
    assert payload["model_execution"] is False
    assert payload["network_access"] is False
    assert payload["golden_or_knowledge_write"] is False
    assert payload["release_state"] == "not_ready_for_release"


def test_assertion_series_h_cli_surface_is_registered() -> None:
    prepare = runner.invoke(app, ["evaluation", "assertion-series-h-campaign-prepare", "--help"])
    assert prepare.exit_code == 0, prepare.output
    assert "--finalist-experiment" in prepare.stdout
    assert "--baseline-experiment" in prepare.stdout
    assert "--partition-plan" in prepare.stdout

    preflight = runner.invoke(app, ["evaluation", "assertion-series-h-preflight", "--help"])
    assert preflight.exit_code == 0, preflight.output
    assert "--readiness" in preflight.stdout
    assert "--campaign" in preflight.stdout
    assert "--gate-profile" in preflight.stdout

    run = runner.invoke(app, ["evaluation", "assertion-series-h-run", "--help"])
    assert run.exit_code == 0, run.output
    assert "--config" in run.stdout
    assert "--prompt-staging-root" in run.stdout

    finalize = runner.invoke(app, ["evaluation", "assertion-series-h-finalize", "--help"])
    assert finalize.exit_code == 0, finalize.output
    assert "--release-decision" in finalize.stdout
    assert "--release-reference" in finalize.stdout
    assert "--qualification-scope" in finalize.stdout


def test_assertion_series_g_preparation_commands_are_registered() -> None:
    commands = {
        "assertion-series-g-verifier-run": ("--experiment-id", "--max-calls"),
        "assertion-series-g-verifier-observations-build": ("--verifier-run", "--output"),
        "assertion-series-g-repetitions-build": ("--variant-id", "--report"),
        "assertion-series-g-gate-profile-build": ("--output", "--max-false-acceptan"),
        "assertion-series-g-freeze-build": ("--partition-plan", "--holdout-campaign"),
    }
    for command, options in commands.items():
        result = runner.invoke(app, ["evaluation", command, "--help"])
        assert result.exit_code == 0, result.output
        for option in options:
            assert option in result.stdout
