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
                            "text": (
                                f"The supplier shall document the safety lifecycle for {key}. "
                                "See Clause 7."
                            ),
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


def workflow(root, manifest, **options):
    return EnrichmentsWorkflowPlanner().plan(
        YamlStandardCatalogReader().read(manifest),
        family_keys=("EXAMPLEA", "EXAMPLEB"),
        catalog_root=root,
        standards_manifest=manifest,
        qualification_manifest=root / "manifests/matrix.yaml",
        knowledge_domain="functional-safety",
        **options,
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
        WorkflowStage.CONTEXT_BASELINE,
        WorkflowStage.KNOWLEDGE_ADOPT,
        WorkflowStage.KNOWLEDGE_PUBLISH,
        WorkflowStage.KNOWLEDGE_RESTORE,
        WorkflowStage.CBOX_REPORT,
        WorkflowStage.ENRICHMENTS_BASELINE,
    ]
    assert len(runner.commands) == count + 6
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


class FailingRoutingProvider:
    generator_id = "baseline-test-provider"

    def __init__(self, *, fail=True):
        self.fail = fail
        self.calls = []

    def input_fingerprint(self, **kwargs):
        return "d" * 64

    def enrich(self, *, clause, document):
        from standards_atlas.application.ports.llm_gateway import LlmResponseError

        self.calls.append(document.key.value)
        if self.fail and document.key.value == "EXAMPLEA":
            raise LlmResponseError("deliberately invalid routing", raw_content="{rejected}")
        return ContextRouting()


def _use_provider(monkeypatch, provider):
    monkeypatch.setattr(
        management,
        "build_context_enrichment_service",
        lambda workspace, **kw: ContextEnrichmentService(
            documents=FileSystemEngineeringDocumentRepository(workspace),
            enricher=provider,
            fresh=kw.get("fresh", False),
            retry_clause_ids=kw.get("retry_clause_ids", ()),
        ),
    )


def _baseline_receipt(root, plan, phase):
    stage = (
        WorkflowStage.CONTEXT_BASELINE if phase == "context" else WorkflowStage.ENRICHMENTS_BASELINE
    )
    step = next(s for s in plan.steps if s.stage is stage)
    return json.loads((root / step.output_paths[0]).read_text())


def test_partial_document_does_not_block_later_documents_or_publication(tmp_path, monkeypatch):
    manifest = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    plan = workflow(tmp_path, manifest)
    runner = BoundaryRunner(plan, monkeypatch, tmp_path)
    provider = FailingRoutingProvider()
    _use_provider(monkeypatch, provider)
    service = build_workflow_service(tmp_path)
    result = service.execute(plan, project_root=tmp_path, runner=runner)
    assert result.completed
    assert provider.calls == ["EXAMPLEA", "EXAMPLEB"]
    for key in ("EXAMPLEA", "EXAMPLEB"):
        assert (tmp_path / f"data/enrichments/{key}.yaml").exists()
    context = _baseline_receipt(tmp_path, plan, "context")
    published = _baseline_receipt(tmp_path, plan, "published")
    for receipt in (context, published):
        assert receipt["status"] == "completed_with_context_failures"
        assert receipt["semantically_verified"] is False
        assert receipt["summary"]["failed"] == 1
        assert receipt["summary"]["succeeded"] == 1
        assert receipt["coverage"]["semantic"] == "all_eligible"
        assert receipt["summary"]["failed_with_retained_value"] == 0
        with ZipFile(receipt["archive"]) as zipped:
            assert "EXAMPLEA-run.json" in " ".join(zipped.namelist())
            failure = json.loads(zipped.read("reports/context/EXAMPLEA-failures.json"))
            assert "deliberately invalid" in failure["failures"][0]["error"]
            inventory = json.loads(zipped.read("manifest.json"))["files"]
            import hashlib

            for item in inventory:
                data = zipped.read(item["path"])
                assert len(data) == item["size"]
                assert hashlib.sha256(data).hexdigest() == item["sha256"]
    with ZipFile(published["archive"]) as zipped:
        assert "qualification/run.zip" in zipped.namelist()
        assert any(name.startswith("knowledge-evidence/") for name in zipped.namelist())
        assert "public/enrichments/EXAMPLEB.yaml" in zipped.namelist()

    from standards_atlas.application.workflow import WorkflowTask
    from standards_atlas.application.workflow.report import WorkflowRunReporter

    report_path, markdown = WorkflowRunReporter().write(
        plan,
        result,
        project_root=tmp_path,
        manifest_paths=(manifest,),
        task=WorkflowTask.ENRICHMENTS,
    )
    report_payload = json.loads(report_path.read_text())
    assert report_payload["status"] == "completed_with_context_failures"
    assert report_payload["baseline"]["archive_sha256"] == published["archive_sha256"]
    assert "not semantic approval" in markdown.read_text()

    # Resume: failed document is revisited; successful checkpoint is reused.
    frozen_context = Path(context["archive"]).read_bytes()
    frozen_published = Path(published["archive"]).read_bytes()
    provider.fail = False
    provider.calls.clear()
    repeated = service.execute(plan, project_root=tmp_path, runner=runner)
    assert repeated.completed
    assert provider.calls == ["EXAMPLEA"]
    assert not (tmp_path / ".atlas/data/evaluation/context-routing/EXAMPLEA-failures.json").exists()
    assert _baseline_receipt(tmp_path, plan, "published")["summary"]["failed"] == 0
    # New receipts never replace the original archives, even as latest reports change.
    assert Path(context["archive"]).read_bytes() == frozen_context
    assert Path(published["archive"]).read_bytes() == frozen_published
    assert _baseline_receipt(tmp_path, plan, "published")["archive"] != published["archive"]


def test_explicit_strict_mode_keeps_the_document_failure_gate(tmp_path, monkeypatch):
    manifest = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    plan = EnrichmentsWorkflowPlanner().plan(
        YamlStandardCatalogReader().read(manifest),
        family_keys=("EXAMPLEA", "EXAMPLEB"),
        catalog_root=tmp_path,
        standards_manifest=manifest,
        qualification_manifest=tmp_path / "manifests/matrix.yaml",
        fail_on_context_failure=True,
    )
    runner = BoundaryRunner(plan, monkeypatch, tmp_path)
    provider = FailingRoutingProvider()
    _use_provider(monkeypatch, provider)
    with pytest.raises(RuntimeError, match="Context routing is incomplete"):
        build_workflow_service(tmp_path).execute(plan, project_root=tmp_path, runner=runner)
    assert provider.calls == ["EXAMPLEA"]
    assert not (tmp_path / "data/enrichments").exists()
    ledger = tmp_path / ".atlas/data/evaluation/context-routing/EXAMPLEA-run.json"
    assert json.loads(ledger.read_text())["summary"]["failed"] == 1


def test_context_archive_survives_a_technical_qualification_failure(tmp_path, monkeypatch):
    manifest = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    plan = workflow(tmp_path, manifest)
    runner = BoundaryRunner(plan, monkeypatch, tmp_path)
    original = runner.run

    def fail_qualification(command, cwd):
        if "qualification-matrix" in command:
            raise OSError("qualification disk failure")
        return original(command, cwd)

    runner.run = fail_qualification
    with pytest.raises(OSError, match="disk failure"):
        build_workflow_service(tmp_path).execute(plan, project_root=tmp_path, runner=runner)
    receipt = _baseline_receipt(tmp_path, plan, "context")
    assert Path(receipt["archive"]).is_file()
    assert receipt["phase"] == "context"
    assert not (tmp_path / "data/enrichments").exists()
    assert not list(tmp_path.rglob("published-baseline.json"))


def test_completed_fresh_baseline_repeats_context_but_not_normalization(tmp_path, monkeypatch):
    manifest = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    plan = workflow(tmp_path, manifest, fresh=True)
    runner = BoundaryRunner(plan, monkeypatch, tmp_path)
    provider = FailingRoutingProvider(fail=False)
    _use_provider(monkeypatch, provider)
    service = build_workflow_service(tmp_path)
    assert service.execute(plan, project_root=tmp_path, runner=runner).completed
    second = service.execute(plan, project_root=tmp_path, runner=runner)
    assert second.completed
    assert provider.calls == ["EXAMPLEA", "EXAMPLEB", "EXAMPLEA", "EXAMPLEB"]
    stages = [s.stage for s in second.executed_steps]
    assert stages.count(WorkflowStage.CONTEXT_ENRICHMENT) == 2
    assert WorkflowStage.NORMALIZE not in stages
    assert _baseline_receipt(tmp_path, plan, "context")["summary"]["succeeded"] == 2


def test_runtime_failure_resumes_after_frozen_partial_context_without_another_model_call(
    tmp_path,
    monkeypatch,
):
    manifest = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = workflow(tmp_path, manifest, fresh=True)

    class InterruptedRunner(BoundaryRunner):
        def run(self, command, cwd):
            step = next(s for s in self.plan.steps if s.command == command)
            if step.stage is WorkflowStage.QUALIFICATION_MATRIX:
                raise RuntimeError("RamaLama endpoint remained available after shutdown")
            return super().run(command, cwd)

    runner = InterruptedRunner(initial, monkeypatch, tmp_path)
    provider = FailingRoutingProvider()
    _use_provider(monkeypatch, provider)
    service = build_workflow_service(tmp_path)
    with pytest.raises(RuntimeError, match="endpoint remained available"):
        service.execute(initial, project_root=tmp_path, runner=runner)
    assert provider.calls == ["EXAMPLEA", "EXAMPLEB"]
    baseline = _baseline_receipt(tmp_path, initial, "context")
    original_archive = Path(baseline["archive"]).read_bytes()
    assert baseline["summary"]["failed"] == 1
    context_receipt = next(s for s in initial.steps if s.stage is WorkflowStage.CONTEXT_BASELINE)
    original_receipt = (tmp_path / context_receipt.output_paths[0]).read_bytes()

    resumed = workflow(tmp_path, manifest, fresh=True, resume_after_context=True)
    runner = BoundaryRunner(resumed, monkeypatch, tmp_path)
    provider.calls.clear()
    _use_provider(monkeypatch, provider)
    result = service.execute(resumed, project_root=tmp_path, runner=runner)
    assert result.completed
    assert provider.calls == []  # Even the previously failed clause is not repeated.
    assert result.executed_steps[0].stage is WorkflowStage.CONTEXT_BASELINE
    assert "--verify-existing" in result.executed_steps[0].command
    assert Path(baseline["archive"]).read_bytes() == original_archive
    assert (tmp_path / context_receipt.output_paths[0]).read_bytes() == original_receipt
    published = _baseline_receipt(tmp_path, resumed, "published")
    assert published["summary"]["failed"] == 1  # Resume is not semantic approval.
    for key in ("EXAMPLEA", "EXAMPLEB"):
        assert (tmp_path / f"data/enrichments/{key}.yaml").exists()
    with ZipFile(published["archive"]) as archive:
        assert archive.read("reports/workflow/context-baseline.json") == original_receipt
