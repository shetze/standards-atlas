"""Real post-Docling pipeline/transfer with synthetic qualification boundary results.

PDF conversion and external inference are deliberately not integration dependencies.
Native Docling reading, normalization, references, alignment, content, taxonomy,
context service, corpus construction, adoption, public/private transfer and resume
are executed. Only provider/policy/archive production is a controlled fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
import yaml
from typer.testing import CliRunner

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.adapters.evaluation.archive_receipt import write_archive_receipt
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.model.knowledge_adoption import (
    ClauseKnowledgeCandidate,
    KnowledgeAdoptionBatch,
)
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.services.context_enrichment_service import ContextEnrichmentService
from standards_atlas.application.workflow import EnrichmentsWorkflowPlanner, WorkflowStage
from standards_atlas.cli import app
from standards_atlas.cli.commands.document_commands import knowledge, management
from standards_atlas.cli.composition import build_workflow_service
from standards_atlas.domain.model import ContextRouting
from standards_atlas.domain.model.enrichment_patch import (
    ClauseEnrichmentPatch,
    SemanticEnrichmentPatch,
)
from standards_atlas.domain.model.knowledge_state import GeneratedAttribute, GenerationMethod
from standards_atlas.shared.hashing import sha256_file

ROOT = Path(__file__).resolve().parents[3]
MATRIX = "multidimensional-semantic-qualification-v6-applicability-presence-v1.yaml"


class EmptyRoutingProvider:
    generator_id = "synthetic-routing"

    def enrich(self, **kwargs):
        return ContextRouting()


def project(root):
    (root / "data").mkdir()
    (root / "manifests").mkdir()
    (root / "cfg").mkdir()
    # Resource-relative corpus policy and tracking use the real project resources.
    (root / "src").symlink_to(ROOT / "src", target_is_directory=True)
    (root / "cfg/context-enrichment.yaml").write_bytes(
        (ROOT / "cfg/context-enrichment.yaml").read_bytes()
    )
    (root / "manifests/matrix.yaml").write_bytes((ROOT / "manifests" / MATRIX).read_bytes())
    families = []
    for key in ("EXAMPLEA", "EXAMPLEB"):
        (root / "data" / key).write_text(
            f'name="{key}"\ndigits=4\nlifecycle_status="published"\n'
            'semanticProfile="functional-safety:1.0.0"\n'
            'structure=(\n "2025 r7"\n)\n#---data---#\n'
            f"TOC;aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;{key}:2025 7;Requirements;r\n"
        )
        families.append(
            {
                "key": key,
                "name": key,
                "organization": "Example",
                "publication_year": 2025,
                "source": {"pdf": f"local/{key}.pdf"},
                "atlasdata": {"path": f"data/{key}"},
            }
        )
        folder = root / ".atlas/data/docling" / key
        folder.mkdir(parents=True)
        (folder / "document.json").write_text(
            json.dumps(
                {
                    "name": key,
                    "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/texts/1"}]},
                    "texts": [
                        {
                            "self_ref": "#/texts/0",
                            "label": "section_header",
                            "level": 1,
                            "text": "7 Requirements",
                            "prov": [{"page_no": 1}],
                        },
                        {
                            "self_ref": "#/texts/1",
                            "label": "text",
                            "text": f"The supplier shall document the safety lifecycle for {key}.",
                            "prov": [{"page_no": 1}],
                        },
                    ],
                }
            )
        )
    manifest = root / "manifests/standards.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "manifest_type": "standards",
                "schema_version": 2,
                "knowledge_domains": [],
                "industry_sectors": [],
                "families": families,
            }
        )
    )
    return manifest


class BoundaryRunner:
    """Run the actual command handlers in-process except the external evaluation boundary."""

    def __init__(self, plan, monkeypatch, root):
        self.plan = plan
        self.root = root
        self.commands = []
        self.sealed_batches = {}
        monkeypatch.setattr(knowledge, "load_qualification_knowledge", self.read_batch)
        monkeypatch.setattr(
            management, "managed_llm_server", lambda *_: SimpleNamespace(start=lambda: None)
        )
        monkeypatch.setattr(
            management,
            "build_context_enrichment_service",
            lambda workspace, **kw: ContextEnrichmentService(
                documents=FileSystemEngineeringDocumentRepository(workspace),
                enricher=EmptyRoutingProvider(),
            ),
        )

    def read_batch(self, path, **kwargs):
        return self.sealed_batches[path.resolve()]

    def run(self, command, cwd):
        self.commands.append(command)
        step = next(s for s in self.plan.steps if s.command == command)
        if step.stage in {
            WorkflowStage.QUALIFICATION_MATRIX,
            WorkflowStage.APPLICABILITY_DECISION_POLICY,
        }:
            for name in step.output_paths:
                path = cwd / name
                if path.suffix in {".json", ".yaml"}:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("{}")
                elif not path.suffix:
                    path.mkdir(parents=True, exist_ok=True)
            return
        if step.stage is WorkflowStage.QUALIFICATION_ARCHIVE:
            self.make_archive(step, cwd)
            return
        result = CliRunner().invoke(app, list(command[3:]))
        if result.exit_code:
            raise RuntimeError(f"{command}\n{result.output}\n{result.exception!r}")

    def make_archive(self, step, cwd):
        corpus_step = next(s for s in self.plan.steps if s.stage is WorkflowStage.CORPUS_BUILD)
        dataset = json.loads((cwd / corpus_step.output_paths[0]).read_text())
        assert {e["input"]["context"]["document_key"] for e in dataset["examples"]} == {
            "EXAMPLEA",
            "EXAMPLEB",
        }
        assert len(dataset["examples"]) == 2
        assert all(e["input"]["context"]["semantic"] == {} for e in dataset["examples"])
        repo = FileSystemEngineeringDocumentRepository(cwd / ".atlas/data")
        candidates = []
        for doc in repo.list():
            for clause in doc.clauses:
                fields = {"applicability_present": False, "role_semantics_present": False}
                candidates.append(
                    ClauseKnowledgeCandidate(
                        document_key=doc.key.value,
                        clause_id=clause.id.value,
                        reference=clause.reference.as_text(),
                        heading=clause.heading,
                        content_hash=normalized_content_hash(clause.plain_text),
                        patch=ClauseEnrichmentPatch(semantic=SemanticEnrichmentPatch(**fields)),
                        attributes=tuple(
                            GeneratedAttribute(
                                path=f"enrichments.semantic.{field}",
                                generator="synthetic-qualified-policy",
                                method=GenerationMethod.IMPORTED,
                            )
                            for field in fields
                        ),
                    )
                )
        archive = cwd / "local/evaluation/synthetic.zip"
        archive.parent.mkdir(parents=True, exist_ok=True)
        matrix_id = step.document.removesuffix("-archive")
        with ZipFile(archive, "w") as zipped:
            zipped.writestr("archive-manifest.json", json.dumps({"matrix_id": matrix_id}))
        self.sealed_batches[archive.resolve()] = KnowledgeAdoptionBatch(
            source_id="synthetic-workflow",
            source_sha256=sha256_file(archive),
            selected_clause_count=2,
            unqualified_clause_count=0,
            candidates=tuple(candidates),
        )
        receipt = cwd / step.command[step.command.index("--receipt") + 1]
        write_archive_receipt(receipt, archive=archive, matrix_id=matrix_id)


def workflow(root, manifest):
    return EnrichmentsWorkflowPlanner().plan(
        YamlStandardCatalogReader().read(manifest),
        family_keys=("EXAMPLEA", "EXAMPLEB"),
        catalog_root=root,
        standards_manifest=manifest,
        qualification_manifest=root / "manifests/matrix.yaml",
        knowledge_domain="functional-safety",
    )


def test_two_documents_normalize_publish_and_repeat_without_duplicate_outputs(
    tmp_path, monkeypatch
):
    manifest = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    plan = workflow(tmp_path, manifest)
    runner = BoundaryRunner(plan, monkeypatch, tmp_path)
    service = build_workflow_service(tmp_path)
    result = service.execute(plan, project_root=tmp_path, runner=runner)
    assert result.completed, result
    snapshots = {}
    for key in ("EXAMPLEA", "EXAMPLEB"):
        normalized = tmp_path / f".atlas/data/normalized/{key}/document.json"
        assert key in normalized.read_text()
        canonical = tmp_path / f".atlas/data/documents/{key}.json"
        assert "synthetic-qualified-policy" in canonical.read_text()
        public = tmp_path / f"data/enrichments/{key}.yaml"
        payload = yaml.safe_load(public.read_text())
        assert payload["schema_version"] == "1.2"
        clauses = payload["clauses"]
        assert len(clauses) == 1 and clauses[0]["heading"] == "Requirements"
        assert clauses[0]["atlasdata_md5"] == "a" * 32
        paths = {a["path"] for a in clauses[0]["attributes"]}
        assert "enrichments.semantic.role_semantics_present" in paths
        assert "enrichments.semantic.role_relations" not in paths
        assert "enrichments.semantic.role_relation_types" not in paths
        assert "shall document" not in public.read_text()
        snapshots[key] = canonical.read_bytes(), public.read_bytes()
    assert list((tmp_path / ".atlas/data/knowledge-evidence").rglob("*.json"))
    count = len(runner.commands)
    repeated = service.execute(plan, project_root=tmp_path, runner=runner)
    assert repeated.completed
    assert [s.stage for s in repeated.executed_steps] == [
        WorkflowStage.KNOWLEDGE_ADOPT,
        WorkflowStage.KNOWLEDGE_PUBLISH,
        WorkflowStage.KNOWLEDGE_RESTORE,
        WorkflowStage.CBOX_REPORT,
    ]
    assert len(runner.commands) == count + 4
    for key, (canonical, public) in snapshots.items():
        assert (tmp_path / f".atlas/data/documents/{key}.json").read_bytes() == canonical
        assert (tmp_path / f"data/enrichments/{key}.yaml").read_bytes() == public


def test_missing_docling_input_stops_without_fallback_or_publication(tmp_path, monkeypatch):
    manifest = project(tmp_path)
    (tmp_path / ".atlas/data/docling/EXAMPLEA/document.json").unlink()
    monkeypatch.chdir(tmp_path)
    plan = workflow(tmp_path, manifest)
    runner = BoundaryRunner(plan, monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="Cannot read Docling JSON"):
        build_workflow_service(tmp_path).execute(plan, project_root=tmp_path, runner=runner)
    assert not (tmp_path / "data/enrichments").exists()
