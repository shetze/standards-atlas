"""Knowledge workflows are explicit and cannot be skipped on stale completion markers."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.adapters.workflow import FileSystemWorkflowArtifactStore
from standards_atlas.application.workflow import (
    ArtifactPolicy,
    EndToEndWorkflowService,
    WorkflowStage,
    WorkflowStep,
)
from standards_atlas.application.workflow.knowledge_plan import (
    knowledge_plan,
    with_knowledge_restore,
)
from standards_atlas.cli import app


@pytest.fixture
def catalog():
    return YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))


def test_knowledge_report_only_is_default_and_no_llm_is_planned(catalog):
    plan = knowledge_plan(
        catalog,
        family_keys=("ISO26262",),
        catalog_root=Path.cwd(),
        manifest=Path("manifests/standards.yaml"),
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].stage is WorkflowStage.CBOX_REPORT
    assert "--write" not in plan.steps[0].command
    assert "ISO26262-11" in plan.steps[0].command
    assert "ISO26262" not in plan.steps[0].command  # family is not a physical document


def test_publication_adoption_restore_are_explicit_and_ordered(catalog):
    plan = knowledge_plan(
        catalog,
        family_keys=("ISO26262",),
        catalog_root=Path.cwd(),
        manifest=Path("manifests/standards.yaml"),
        adopt_run=Path("local/run.zip"),
        restore=True,
        publish=True,
        strict_evidence=True,
    )
    assert [item.stage for item in plan.steps] == [
        WorkflowStage.KNOWLEDGE_RESTORE,
        WorkflowStage.KNOWLEDGE_ADOPT,
        WorkflowStage.KNOWLEDGE_PUBLISH,
        WorkflowStage.KNOWLEDGE_RESTORE,
        WorkflowStage.CBOX_REPORT,
    ]
    assert all("--available-only" in item.command for item in plan.steps)
    for step in plan.steps:
        assert "--write" in step.command or step.stage is WorkflowStage.CBOX_REPORT
        assert not any(
            token in step.command for token in ("qualification-matrix", "enrich-context")
        )
        assert not FileSystemWorkflowArtifactStore().outputs_exist(step, Path.cwd())


def test_opt_in_restore_precedes_context_and_consumers(catalog):
    normal = EndToEndWorkflowService().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        include_semantic_enrichment=True,
    )
    assert not any(item.stage is WorkflowStage.KNOWLEDGE_RESTORE for item in normal.steps)
    restored = with_knowledge_restore(normal, manifest=Path("manifests/standards.yaml"))
    stages = [item.stage for item in restored.steps]
    assert stages.index(WorkflowStage.TAXONOMY) < stages.index(WorkflowStage.KNOWLEDGE_RESTORE)
    assert stages.index(WorkflowStage.KNOWLEDGE_RESTORE) < stages.index(
        WorkflowStage.CONTEXT_ENRICHMENT
    )
    assert stages.index(WorkflowStage.CONTEXT_ENRICHMENT) < stages.index(WorkflowStage.CBOX_REPORT)
    assert stages.index(WorkflowStage.CBOX_REPORT) < stages.index(WorkflowStage.MARKDOWN)
    assert WorkflowStage.KNOWLEDGE_PUBLISH not in stages


@pytest.mark.parametrize("task", ["documents", "qualification"])
def test_default_tasks_cannot_publish_by_accidental_flag(task):
    result = CliRunner().invoke(
        app,
        [
            "workflow",
            "plan",
            "--manifests",
            "manifests/standards.yaml",
            "--task",
            task,
            "--publish-enrichments",
        ],
    )
    assert result.exit_code != 0
    assert "require --task knowledge" in result.output


def test_strict_evidence_needs_a_restore_or_publication():
    result = CliRunner().invoke(
        app,
        [
            "workflow",
            "plan",
            "--manifests",
            "manifests/standards.yaml",
            "--task",
            "knowledge",
            "--strict-evidence",
        ],
    )
    assert result.exit_code != 0
    assert "requires restore or publication" in result.output


def test_knowledge_cli_plan_has_physical_source_selection():
    result = CliRunner().invoke(
        app,
        [
            "workflow",
            "plan",
            "--manifests",
            "manifests/standards.yaml",
            "--task",
            "knowledge",
            "--family",
            "ISO26262",
            "--publish-enrichments",
        ],
    )
    assert result.exit_code == 0, result.output
    for command in ("export-enrichments", "import-enrichments", "cbox-report"):
        assert command in result.output
    assert "ISO26262-11" in result.output


def input_step(stage):
    return WorkflowStep(
        "EXAMPLE",
        "EXAMPLE",
        stage,
        ("uv", "run", "standards-atlas", "test"),
        ArtifactPolicy.DERIVED,
        output_paths=(".atlas/work/workflow/example.complete",),
    )


@pytest.mark.parametrize("stage", [WorkflowStage.CORPUS_BUILD, WorkflowStage.CONTEXT_ENRICHMENT])
def test_source_changes_invalidate_existing_markers(tmp_path, stage):
    source = tmp_path / ".atlas/data/documents/EXAMPLE.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"document": {"clauses": [{"baseline": {"heading": "old"}}]}}))
    step = input_step(stage)
    store = FileSystemWorkflowArtifactStore()
    store.record_completion(step, tmp_path)
    assert store.outputs_exist(step, tmp_path)
    source.write_text(source.read_text().replace("old", "new"))
    assert not store.outputs_exist(step, tmp_path)
    store.record_completion(step, tmp_path)
    assert store.outputs_exist(step, tmp_path)


def test_context_checkpoint_ignores_other_document_enrichment_not_its_baseline(tmp_path):
    source = tmp_path / ".atlas/data/documents/OTHER.json"
    source.parent.mkdir(parents=True)
    content = {
        "document": {
            "clauses": [
                {"baseline": {"heading": "term"}, "enrichments": {"context_routing": "old"}}
            ]
        }
    }
    source.write_text(json.dumps(content))
    step = input_step(WorkflowStage.CONTEXT_ENRICHMENT)
    store = FileSystemWorkflowArtifactStore()
    store.record_completion(step, tmp_path)
    content["document"]["clauses"][0]["enrichments"]["context_routing"] = "new"
    source.write_text(json.dumps(content))
    assert store.outputs_exist(step, tmp_path)
    content["document"]["clauses"][0]["baseline"]["heading"] = "another term"
    source.write_text(json.dumps(content))
    assert not store.outputs_exist(step, tmp_path)


def test_context_config_changes_invalidate_but_renderer_changes_do_not(tmp_path):
    config = tmp_path / "cfg/context-enrichment.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("model: first\n")
    step = input_step(WorkflowStage.CONTEXT_ENRICHMENT)
    store = FileSystemWorkflowArtifactStore()
    store.record_completion(step, tmp_path)
    renderer = (
        tmp_path / "src/standards_atlas/application/semantic_qualification/context_projection.py"
    )
    renderer.parent.mkdir(parents=True)
    renderer.write_text("# different prose only\n")
    assert store.outputs_exist(step, tmp_path)
    config.write_text("model: second\n")
    assert not store.outputs_exist(step, tmp_path)


def test_matrix_tracks_corpus_and_prompt_resources(tmp_path):
    step = input_step(WorkflowStage.QUALIFICATION_MATRIX)
    dataset = tmp_path / ".atlas/data/evaluation/corpora/test/dataset.json"
    dataset.parent.mkdir(parents=True)
    dataset.write_text('{"examples": []}')
    store = FileSystemWorkflowArtifactStore()
    store.record_completion(step, tmp_path)
    assert store.outputs_exist(step, tmp_path)
    dataset.write_text('{"examples": [1]}')
    assert not store.outputs_exist(step, tmp_path)
    store.record_completion(step, tmp_path)
    prompt = tmp_path / "src/standards_atlas/resources/semantic/prompts/test/user.txt"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("New prompt")
    assert not store.outputs_exist(step, tmp_path)


def test_matrix_frame_selection_changes_invalidate_but_renderer_prose_does_not(tmp_path):
    step = input_step(WorkflowStage.QUALIFICATION_MATRIX)
    store = FileSystemWorkflowArtifactStore()
    root = tmp_path / "src/standards_atlas/application/semantic_qualification"
    root.mkdir(parents=True)
    (root / "context_framing.py").write_text("# selection v1")
    store.record_completion(step, tmp_path)
    (root / "context_projection.py").write_text("# another renderer")
    assert store.outputs_exist(step, tmp_path)
    (root / "context_framing.py").write_text("# selection v2")
    assert not store.outputs_exist(step, tmp_path)
