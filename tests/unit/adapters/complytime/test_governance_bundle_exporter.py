from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from standards_atlas.adapters.complytime import ComplyTimeGovernanceBundleExporter
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


def test_governance_bundle_contains_linked_gemara_sources_and_manifest(
    tmp_path: Path,
) -> None:
    target = tmp_path / "bundle"

    result = ComplyTimeGovernanceBundleExporter().export(_document(), target)

    assert result == target
    assert sorted(path.name for path in target.iterdir()) == [
        "controls.yaml",
        "guidance.yaml",
        "lineage.json",
        "manifest.yaml",
        "traceability.json",
    ]

    manifest = yaml.safe_load((target / "manifest.yaml").read_text(encoding="utf-8"))
    guidance = yaml.safe_load((target / "guidance.yaml").read_text(encoding="utf-8"))
    controls = yaml.safe_load((target / "controls.yaml").read_text(encoding="utf-8"))
    traceability = json.loads((target / "traceability.json").read_text(encoding="utf-8"))

    assert manifest["schema-version"] == "1.0"
    assert manifest["bundle-id"] == "sample-1-governance"
    assert manifest["gemara-version"] == GEMARA_SPEC_VERSION
    assert manifest["source"]["document-key"] == "SAMPLE-1"
    assert manifest["source"]["version"] == "2026-09"
    assert manifest["guidance"]["catalog-id"] == "sample-1"
    assert manifest["controls"]["catalog-id"] == "sample-1-controls"

    assert guidance["metadata"]["id"] == "sample-1"
    assert controls["metadata"]["mapping-references"][0]["id"] == "sample-1"
    assert controls["controls"][0]["guidelines"][0]["reference-id"] == "sample-1"
    assert traceability["guidance"]["gemara_catalog_id"] == "sample-1"
    assert traceability["controls"]["guidance_catalog_id"] == "sample-1"

    for artifact_name in ("guidance", "controls", "traceability"):
        artifact = manifest[artifact_name]
        content = (target / artifact["path"]).read_bytes()
        assert artifact["sha256"] == hashlib.sha256(content).hexdigest()


def test_governance_bundle_is_deterministic_on_reexport(tmp_path: Path) -> None:
    target = tmp_path / "bundle"
    exporter = ComplyTimeGovernanceBundleExporter()

    exporter.export(_document(), target)
    first = {
        path.name: path.read_bytes() for path in target.iterdir() if path.name != "lineage.json"
    }

    exporter.export(_document(), target)
    second = {
        path.name: path.read_bytes() for path in target.iterdir() if path.name != "lineage.json"
    }

    assert first == second


def test_governance_bundle_refuses_existing_target_without_replace(
    tmp_path: Path,
) -> None:
    target = tmp_path / "bundle"
    target.mkdir()

    try:
        ComplyTimeGovernanceBundleExporter().export(
            _document(),
            target,
            replace_existing=False,
        )
    except FileExistsError as exc:
        assert str(target) in str(exc)
    else:
        raise AssertionError("Expected FileExistsError")


def test_governance_bundle_does_not_emit_complypack_configuration(
    tmp_path: Path,
) -> None:
    target = tmp_path / "bundle"

    ComplyTimeGovernanceBundleExporter().export(_document(), target)

    assert not (target / "complypack.yaml").exists()
