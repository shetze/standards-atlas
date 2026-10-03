from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.assertion_qualification.assertion_review import (
    load_assertion_review_package,
)
from standards_atlas.application.assertion_qualification.reference_corpus import (
    ExposureKind,
    ReferenceCandidate,
    ReferenceCorpusRequest,
    ReferenceExposure,
    build_reference_corpus_plan,
)
from standards_atlas.cli.main import app
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TextBlock,
)

runner = CliRunner()


def _document(key: str, clause_id: str, reference: str, text: str) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value=key),
        title=key,
        document_type=DocumentType.OTHER,
        clauses=(
            Clause(
                id=ClauseId(value=clause_id),
                reference=StandardReference(standard=key, clause=reference),
                clause_type=ClauseType.CLAUSE,
                content=(TextBlock(id=f"{clause_id}-text", text=text),),
            ),
        ),
    )


def _plan(tmp_path: Path):
    plan = build_reference_corpus_plan(
        ReferenceCorpusRequest(
            plan_id="review-smoke",
            plan_version="1",
            seed=3,
            development_limit=1,
            holdout_limit=1,
            candidates=(
                ReferenceCandidate(
                    document_key="DOC",
                    clause_id="c1",
                    reference="1",
                    clause_type="requirement",
                    primary_source_group="dev-group",
                    bearing_source_groups=("dev-group",),
                    exposures=(
                        ReferenceExposure(
                            kind=ExposureKind.LEGACY_DEVELOPMENT,
                            reference="historical-development",
                        ),
                    ),
                ),
                ReferenceCandidate(
                    document_key="HOLD",
                    clause_id="h1",
                    reference="1",
                    clause_type="requirement",
                    primary_source_group="hold-group",
                    bearing_source_groups=("hold-group",),
                ),
            ),
        )
    )
    path = tmp_path / "partition-and-exposure.json"
    path.write_text(json.dumps(plan.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return plan, path


def test_build_uses_bound_plan_reconstructs_source_package_and_derives_ontology(tmp_path: Path):
    workspace = tmp_path / "workspace"
    documents = FileSystemEngineeringDocumentRepository(workspace)
    documents.save(_document("DOC", "c1", "1", "The report shall be recorded."))
    documents.save(_document("HOLD", "h1", "1", "Independent holdout source."))
    plan, plan_path = _plan(tmp_path)

    manifest = tmp_path / "review-build.json"
    manifest.write_text(
        json.dumps(
            {
                "contract_id": "assertion-review-workbench-build-v1",
                "id": "review",
                "version": "1",
                "corpus_plan": plan_path.name,
                "ontology_versions": [
                    "standards-atlas-core@2.0.0",
                    "functional-safety@2.1.0",
                ],
                "cases": [{"document_key": "DOC", "clause_id": "c1"}],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "review-package"

    result = runner.invoke(
        app,
        [
            "evaluation",
            "assertion-review-workbench-build",
            "--manifest",
            str(manifest),
            "--workspace",
            str(workspace),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    package, state = load_assertion_review_package(output)
    assert package.corpus_plan_sha256 == plan.plan_sha256
    assert package.cases[0].partition.value == "development"
    assert package.cases[0].source_group == "dev-group"
    assert state.revision == 0
    assert any(item.label == "WorkProduct" for item in package.class_options)
    assert any(item.label == "requires" for item in package.predicate_options)
    source_files = tuple((workspace / "context-source-packages").glob("*.json"))
    assert len(source_files) == 1
    assert package.cases[0].source_package_sha256 == f"sha256:{source_files[0].stem}"


def test_build_rejects_tampered_corpus_plan(tmp_path: Path):
    workspace = tmp_path / "workspace"
    documents = FileSystemEngineeringDocumentRepository(workspace)
    documents.save(_document("DOC", "c1", "1", "The report shall be recorded."))
    documents.save(_document("HOLD", "h1", "1", "Independent holdout source."))
    _, plan_path = _plan(tmp_path)
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["development"][0]["source_group"] = "tampered"
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    manifest = tmp_path / "review-build.json"
    manifest.write_text(
        json.dumps(
            {
                "contract_id": "assertion-review-workbench-build-v1",
                "id": "review",
                "version": "1",
                "corpus_plan": plan_path.name,
                "ontology_versions": ["standards-atlas-core@2.0.0"],
                "cases": [{"document_key": "DOC", "clause_id": "c1"}],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "evaluation",
            "assertion-review-workbench-build",
            "--manifest",
            str(manifest),
            "--workspace",
            str(workspace),
            "--output",
            str(tmp_path / "review-package"),
        ],
    )

    assert result.exit_code != 0
    assert "plan_sha256 does not match plan content" in result.output


def test_build_without_case_filter_prepares_development_and_holdout(tmp_path: Path):
    workspace = tmp_path / "workspace"
    documents = FileSystemEngineeringDocumentRepository(workspace)
    documents.save(_document("DOC", "c1", "1", "The report shall be recorded."))
    documents.save(_document("HOLD", "h1", "1", "Independent holdout source."))
    _, plan_path = _plan(tmp_path)
    manifest = tmp_path / "review-build.json"
    manifest.write_text(
        json.dumps(
            {
                "contract_id": "assertion-review-workbench-build-v1",
                "id": "review-all",
                "version": "1",
                "corpus_plan": plan_path.name,
                "ontology_versions": ["standards-atlas-core@2.0.0"],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "review-package"

    result = runner.invoke(
        app,
        [
            "evaluation",
            "assertion-review-workbench-build",
            "--manifest",
            str(manifest),
            "--workspace",
            str(workspace),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    package, _ = load_assertion_review_package(output)
    assert {case.partition.value for case in package.cases} == {"development", "holdout"}
    assert len(tuple((workspace / "context-source-packages").glob("*.json"))) == 2
