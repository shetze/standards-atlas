from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from standards_atlas.adapters.atlasdata.knowledge_contract import (
    AtlasDataKnowledge,
    ClauseKnowledge,
    PublishedAttribute,
)
from standards_atlas.adapters.atlasdata.knowledge_evidence import digest
from standards_atlas.adapters.atlasdata.knowledge_transfer import (
    AtlasDataKnowledgeService,
    knowledge_bytes,
    read_knowledge,
    structure_digest,
)
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.catalog.atlasdata_binding import atlasdata_bindings
from standards_atlas.application.catalog.models import StandardCatalog
from standards_atlas.cli import app


def _world(tmp_path: Path):
    public = tmp_path / "data"
    public.mkdir()
    (public / "EXAMPLE").write_text(
        'name="Example"\n'
        "digits=4\n"
        "partShift=0\n"
        "partDigits=0\n"
        "oyr=2025\n"
        'lifecycle_status="published"\n'
        'structure=(\n "2025 1-0 1-1"\n)\n'
        "#---data---#\n"
        "TOC;aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;Example-1:2025 0;Canonical Part Title;u\n"
        "TOC;bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb;Example-1:2025 1;Scope;r\n",
        encoding="utf-8",
    )
    payload = {
        "manifest_type": "standards",
        "schema_version": 2,
        "knowledge_domains": [],
        "industry_sectors": [],
        "families": [
            {
                "key": "EXAMPLE",
                "name": "Example",
                "organization": "Example",
                "publication_year": 2025,
                "atlasdata": {"path": "data/EXAMPLE"},
                "parts": [
                    {
                        "part": "1",
                        "key": "EXAMPLE-1",
                        "title": "Manifest Short Title",
                        "source": {"pdf": "local/example-1.pdf"},
                    }
                ],
            }
        ],
    }
    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests/standards.yaml").write_text(yaml.safe_dump(payload))
    bindings = atlasdata_bindings(StandardCatalog.model_validate(payload), root=tmp_path)
    repository = FileSystemEngineeringDocumentRepository(tmp_path / ".atlas/data")
    service = AtlasDataKnowledgeService(
        documents=repository,
        bindings=bindings,
        evidence_root=tmp_path / ".atlas/data/knowledge-evidence",
    )
    binding = bindings["EXAMPLE-1"]
    current = service._skeleton(binding)
    assert current.title == "Canonical Part Title"
    legacy_heading = "Part 1"
    legacy = current.model_copy(
        update={
            "clauses": tuple(
                clause.with_baseline_updates(heading=legacy_heading)
                if clause.reference.clause == "0"
                else clause
                for clause in current.clauses
            )
        }
    )
    md5s = service._atlasdata_md5s(binding, current)
    root = legacy.clauses[0]
    old_heading_sha256 = digest(legacy_heading.encode())
    manifest = AtlasDataKnowledge(
        document_key="EXAMPLE-1",
        family_key="EXAMPLE",
        atlasdata_file="EXAMPLE",
        selection_part="1",
        publication_year=2025,
        structure_sha256=structure_digest(legacy),
        clauses=(
            ClauseKnowledge(
                clause_id=root.id.value,
                atlasdata_md5=md5s[root.id.value],
                reference=root.reference,
                heading=legacy_heading,
                heading_sha256=old_heading_sha256,
                atlasdata_heading_sha256=old_heading_sha256,
                attributes=(
                    PublishedAttribute(
                        path="enrichments.semantic.applicability_present",
                        origin="unattributed",
                        value=True,
                    ),
                ),
            ),
        ),
    )
    binding.enrichments_path.parent.mkdir(parents=True, exist_ok=True)
    binding.enrichments_path.write_bytes(knowledge_bytes(manifest))
    return tmp_path, repository, service, binding, current, legacy, manifest


def test_rebind_accepts_only_exact_legacy_part_root_and_preserves_knowledge(tmp_path: Path):
    root, repository, service, binding, current, _, before = _world(tmp_path)
    original_bytes = binding.enrichments_path.read_bytes()

    preview = service.rebind_root_titles(document_keys=("EXAMPLE-1",), write=False)
    assert preview.operation == "rebind"
    assert preview.schema_version == "1.1"
    assert preview.status_counts == {"rebound": 1}
    assert binding.enrichments_path.read_bytes() == original_bytes

    result = service.rebind_root_titles(document_keys=("EXAMPLE-1",), write=True)
    assert result.written_targets == (str(binding.enrichments_path),)
    after = read_knowledge(binding.enrichments_path)
    assert after.structure_sha256 == structure_digest(current)
    assert after.clauses[0].heading == "Canonical Part Title"
    assert after.clauses[0].attributes == before.clauses[0].attributes
    assert after.clauses[0].content_sha256 == before.clauses[0].content_sha256

    # The rebound sidecar is immediately restorable under strict evidence.
    service.import_(document_keys=("EXAMPLE-1",), write=True, strict_evidence=True)
    restored = repository.load(current.key)
    assert restored.title == "Canonical Part Title"
    assert restored.clauses[0].heading == "Canonical Part Title"
    assert restored.clauses[0].enrichments.semantic.applicability_present is True


def test_rebind_is_idempotent_for_current_sidecar(tmp_path: Path):
    _, _, service, binding, _, _, _ = _world(tmp_path)
    service.rebind_root_titles(document_keys=("EXAMPLE-1",), write=True)
    rebound = binding.enrichments_path.read_bytes()

    second = service.rebind_root_titles(document_keys=("EXAMPLE-1",), write=True)
    assert second.changed_targets == ()
    assert second.written_targets == ()
    assert second.status_counts == {}
    assert binding.enrichments_path.read_bytes() == rebound


def test_rebind_rejects_any_non_root_structural_drift_without_writing(tmp_path: Path):
    _, _, service, binding, current, legacy, manifest = _world(tmp_path)
    original = binding.enrichments_path.read_bytes()
    clauses = list(legacy.clauses)
    clauses[1] = clauses[1].with_baseline_updates(heading="Changed Scope")
    drifted = legacy.model_copy(update={"clauses": tuple(clauses)})
    invalid = manifest.model_copy(update={"structure_sha256": structure_digest(drifted)})
    binding.enrichments_path.write_bytes(knowledge_bytes(invalid))
    damaged = binding.enrichments_path.read_bytes()

    with pytest.raises(ValueError, match="not the deterministic legacy Part-N projection"):
        service.rebind_root_titles(document_keys=("EXAMPLE-1",), write=True)
    assert binding.enrichments_path.read_bytes() == damaged
    assert binding.enrichments_path.read_bytes() != original
    assert structure_digest(current) != invalid.structure_sha256


def test_rebind_rejects_root_record_not_bound_to_legacy_heading(tmp_path: Path):
    _, _, service, binding, _, _, manifest = _world(tmp_path)
    record = manifest.clauses[0].model_copy(update={"heading": "Other"})
    invalid = manifest.model_copy(update={"clauses": (record,)})
    binding.enrichments_path.write_bytes(knowledge_bytes(invalid))
    before = binding.enrichments_path.read_bytes()

    with pytest.raises(ValueError, match="root record is not bound"):
        service.rebind_root_titles(document_keys=("EXAMPLE-1",), write=True)
    assert binding.enrichments_path.read_bytes() == before


def test_cli_rebind_has_dry_run_and_explicit_write(tmp_path: Path):
    root, _, _, binding, current, _, _ = _world(tmp_path)
    runner = CliRunner()
    command = [
        "atlasdata",
        "rebind-enrichments",
        "--root",
        str(root),
        "--document",
        "EXAMPLE-1",
        "--output",
        "local/rebind.json",
    ]
    before = binding.enrichments_path.read_bytes()
    preview = runner.invoke(app, command)
    assert preview.exit_code == 0, preview.output
    assert "Dry run only" in preview.output
    assert binding.enrichments_path.read_bytes() == before
    report = yaml.safe_load((root / "local/rebind.json").read_text())
    assert report["schema_version"] == "1.1"
    assert report["operation"] == "rebind"

    applied = runner.invoke(app, [*command, "--write"])
    assert applied.exit_code == 0, applied.output
    rebound = read_knowledge(binding.enrichments_path)
    assert rebound.structure_sha256 == structure_digest(current)
