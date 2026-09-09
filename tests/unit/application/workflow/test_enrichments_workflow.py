"""Explicit post-Docling publication and source-scoped, resumable handoff."""

import json
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.adapters.evaluation.archive_receipt import (
    resolve_archive_receipt,
    write_archive_receipt,
)
from standards_atlas.adapters.workflow import FileSystemWorkflowArtifactStore
from standards_atlas.application.workflow import (
    EnrichmentsWorkflowPlanner,
    WorkflowExecutor,
    WorkflowRecovery,
    WorkflowStage,
)
from standards_atlas.cli import app

MANIFEST = Path("manifests/standards.yaml")
MATRIX = Path("manifests/multidimensional-semantic-qualification-v6-applicability-presence-v1.yaml")


def plan(**options):
    return EnrichmentsWorkflowPlanner().plan(
        YamlStandardCatalogReader().read(MANIFEST),
        catalog_root=Path.cwd(),
        standards_manifest=MANIFEST,
        qualification_manifest=MATRIX,
        **{"family_keys": ("EN50716",), **options},
    )


def step_for(stage, **options):
    return next(step for step in plan(**options).steps if step.stage is stage)


def test_complete_explicit_chain_and_exact_archive_handoff():
    steps = plan().steps
    stages = [step.stage for step in steps]
    assert WorkflowStage.DOCLING not in stages
    assert WorkflowStage.MARKDOWN not in stages
    assert WorkflowStage.DOORSTOP not in stages
    assert stages[-5:] == [
        WorkflowStage.QUALIFICATION_ARCHIVE,
        WorkflowStage.KNOWLEDGE_ADOPT,
        WorkflowStage.KNOWLEDGE_PUBLISH,
        WorkflowStage.KNOWLEDGE_RESTORE,
        WorkflowStage.CBOX_REPORT,
    ]
    corpus = step_for(WorkflowStage.CORPUS_BUILD)
    assert "--all-clauses" in corpus.command and "--count" not in corpus.command
    assert "--source-only-context" in corpus.command
    assert corpus.command[corpus.command.index("--document") + 1] == "EN50716"
    archive, adopt = steps[-5:-3]
    receipt = archive.command[archive.command.index("--receipt") + 1]
    assert adopt.command[adopt.command.index("--run-receipt") + 1] == receipt
    assert "--run" not in adopt.command
    for step in steps[-3:]:
        assert "--available-only" not in step.command  # Cannot silently skip publication.


def test_context_runs_after_all_selected_document_taxonomies():
    stages = [step.stage for step in plan(family_keys=("EN50716", "EN50657")).steps]
    assert max(i for i, s in enumerate(stages) if s is WorkflowStage.TAXONOMY) < min(
        i for i, s in enumerate(stages) if s is WorkflowStage.CONTEXT_ENRICHMENT
    )


def test_physical_parts_not_family_skeleton_are_corpus_and_publication_targets():
    corpus = step_for(WorkflowStage.CORPUS_BUILD, family_keys=("ISO26262",))
    assert "ISO26262-11" in corpus.command and "ISO26262" not in corpus.command
    selected = [corpus.command[i + 1] for i, c in enumerate(corpus.command) if c == "--document"]
    assert len(selected) == 11  # Physical parts declared by this snapshot.
    assert selected == sorted(set(selected))


def test_sample_run_is_isolated_from_full_population():
    full = step_for(WorkflowStage.CORPUS_BUILD)
    sample = step_for(WorkflowStage.CORPUS_BUILD, corpus_count=50, limit=10)
    assert sample.command[sample.command.index("--count") + 1] == "50"
    assert sample.output_paths != full.output_paths
    full_matrix = step_for(WorkflowStage.QUALIFICATION_MATRIX)
    sample_matrix = step_for(WorkflowStage.QUALIFICATION_MATRIX, corpus_count=50, limit=10)
    assert full_matrix.output_paths[-1] != sample_matrix.output_paths[-1]
    assert plan().steps == plan().steps


def test_regenerate_docling_and_restore_remain_explicit():
    p = plan(regenerate_docling=True, restore_enrichments=True, strict_evidence=True)
    assert p.force
    assert any(s.stage is WorkflowStage.DOCLING for s in p.steps)
    stages = [s.stage for s in p.steps]
    assert stages.index(WorkflowStage.KNOWLEDGE_RESTORE) < stages.index(
        WorkflowStage.CONTEXT_ENRICHMENT
    )
    assert "--strict-evidence" in p.steps[-2].command


def test_manifest_without_final_policy_is_rejected():
    with pytest.raises(ValueError, match="final consensus"):
        EnrichmentsWorkflowPlanner().plan(
            YamlStandardCatalogReader().read(MANIFEST),
            family_keys=("EN50716",),
            catalog_root=Path.cwd(),
            standards_manifest=MANIFEST,
            qualification_manifest=Path(
                "manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml"
            ),
        )


def test_missing_atlasdata_binding_is_not_silently_omitted():
    with pytest.raises(ValueError, match="reviewed AtlasData bindings"):
        plan(family_keys=("EN50716", "IEC29100"))


def test_cli_exposes_new_task_and_keeps_qualification_default_sample():
    common = ["workflow", "plan", "--manifests", f"{MANIFEST},{MATRIX}", "--family", "EN50716"]
    result = CliRunner().invoke(app, [*common, "--task", "enrichments"])
    assert result.exit_code == 0, result.output
    assert "--all-clauses" in result.output and "--run-receipt" in result.output
    result = CliRunner().invoke(app, [*common, "--task", "qualification"])
    assert result.exit_code == 0, result.output
    assert "--count 500" in result.output and "export-enrichments" not in result.output


def test_global_tail_waits_for_an_open_alignment_gate(tmp_path):
    p = plan()
    review = next(step for step in p.steps if step.stage is WorkflowStage.REVIEW)
    p = replace(p, steps=(review, *p.steps[-5:]))
    commands = []

    class Runner:
        def run(self, command, cwd):
            commands.append(command)

    result = WorkflowExecutor(WorkflowRecovery(FileSystemWorkflowArtifactStore())).execute(
        p, project_root=tmp_path, runner=Runner()
    )
    assert not result.completed
    assert commands == [review.command]


def archive(tmp_path, matrix="matrix"):
    path = tmp_path / "run.zip"
    with ZipFile(path, "w") as output:
        output.writestr("archive-manifest.json", json.dumps({"matrix_id": matrix}))
    return path


def test_receipt_verifies_matrix_and_exact_archive_bytes(tmp_path):
    path = archive(tmp_path)
    receipt = tmp_path / "receipt.json"
    write_archive_receipt(receipt, archive=path, matrix_id="matrix")
    assert resolve_archive_receipt(receipt) == path
    with pytest.raises(ValueError, match="matrix differs"):
        write_archive_receipt(receipt, archive=path, matrix_id="another")
    assert resolve_archive_receipt(receipt) == path  # Failed writes do not replace the receipt.
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="checksum"):
        resolve_archive_receipt(receipt)


def test_adoption_rejects_ambiguous_handoff_and_corrupt_archive(tmp_path):
    path = archive(tmp_path)
    receipt = tmp_path / "receipt.json"
    write_archive_receipt(receipt, archive=path, matrix_id="matrix")
    result = CliRunner().invoke(
        app,
        [
            "document",
            "adopt-qualification",
            "--run",
            str(path),
            "--run-receipt",
            str(receipt),
        ],
    )
    assert result.exit_code == 2 and "exactly one" in result.output
    path.write_bytes(b"not the sealed archive")
    result = CliRunner().invoke(
        app,
        [
            "document",
            "adopt-qualification",
            "--run-receipt",
            str(receipt),
            "--write",
        ],
    )
    assert result.exit_code == 2 and "checksum" in result.output


def test_archive_checkpoint_reuses_only_unchanged_verified_inputs(tmp_path):
    step = step_for(WorkflowStage.QUALIFICATION_ARCHIVE)
    receipt = tmp_path / step.command[step.command.index("--receipt") + 1]
    matrix = step.document.removesuffix("-archive")
    path = archive(tmp_path, matrix)
    write_archive_receipt(receipt, archive=path, matrix_id=matrix)
    run = tmp_path / step.command[step.command.index("--output") + 1] / matrix
    run.mkdir(parents=True)
    source = run / "final-consensus-report.json"
    source.write_text("before")
    store = FileSystemWorkflowArtifactStore()
    store.record_completion(step, tmp_path)
    assert store.outputs_exist(step, tmp_path)
    source.write_text("after")
    assert not store.outputs_exist(step, tmp_path)
    store.record_completion(step, tmp_path)
    path.unlink()
    assert not store.outputs_exist(step, tmp_path)


def test_new_corpus_checkpoint_ignores_output_feedback_and_unselected_docs(tmp_path):
    step = step_for(WorkflowStage.CORPUS_BUILD)
    source = tmp_path / ".atlas/data/documents/EN50716.json"
    source.parent.mkdir(parents=True)
    payload = {
        "document": {
            "clauses": [
                {
                    "baseline": {"heading": "One"},
                    "enrichments": {"semantic": {"value": False}},
                    "provenance": {"generated_attributes": [{"path": "enrichments.semantic.foo"}]},
                }
            ]
        }
    }
    source.write_text(json.dumps(payload))
    for name in step.output_paths:
        output = tmp_path / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("{}")
    store = FileSystemWorkflowArtifactStore()
    store.record_completion(step, tmp_path)
    payload["document"]["clauses"][0]["enrichments"]["semantic"]["value"] = True
    source.write_text(json.dumps(payload))
    (source.parent / "OTHER.json").write_text("unrelated")
    assert store.outputs_exist(step, tmp_path)
    payload["document"]["clauses"][0]["baseline"]["heading"] = "Two"
    source.write_text(json.dumps(payload))
    assert not store.outputs_exist(step, tmp_path)


def test_in_process_execution_does_not_use_cli_subprocesses(tmp_path, monkeypatch):
    import subprocess

    import typer

    from standards_atlas.cli.workflow_runner import InProcessWorkflowCommandRunner

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected CLI subprocess")

    monkeypatch.setattr(subprocess, "run", forbidden)
    before = Path.cwd()
    InProcessWorkflowCommandRunner().run(
        ("uv", "run", "standards-atlas", "catalog", "validate", str(MANIFEST.resolve())), tmp_path
    )
    assert Path.cwd() == before
    with pytest.raises(typer.Exit) as exc:
        InProcessWorkflowCommandRunner().run(
            ("uv", "run", "standards-atlas", "normalize", "run", "MISSING"), tmp_path
        )
    assert exc.value.exit_code == 2
    assert Path.cwd() == before


def test_context_failures_are_fatal_only_with_explicit_workflow_policy(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from standards_atlas.cli.commands.document_commands import management

    config = Path("cfg/context-enrichment.yaml").resolve()
    monkeypatch.setattr(
        management, "managed_llm_server", lambda *_: SimpleNamespace(start=lambda: None)
    )
    result = SimpleNamespace(
        document=SimpleNamespace(key=SimpleNamespace(value="DOC")),
        clauses_enriched=0,
        subject_clauses=1,
        subjects_identified=0,
        subjects_ambiguous=0,
        candidates=1,
        context_enrichment_failures=1,
    )
    monkeypatch.setattr(
        management,
        "build_context_enrichment_service",
        lambda *args, **kw: SimpleNamespace(enrich=lambda *_: result),
    )
    args = ["document", "enrich-context", "DOC", "--context-config", str(config)]
    assert CliRunner().invoke(app, args).exit_code == 0
    failure = CliRunner().invoke(app, [*args, "--fail-on-failure"])
    assert failure.exit_code == 2 and "incomplete" in failure.output
    assert "--fail-on-failure" in step_for(WorkflowStage.CONTEXT_ENRICHMENT).command
