from pathlib import Path

import yaml

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.adapters.workflow.cli_renderer import CliWorkflowOperationRenderer
from standards_atlas.application.semantic_qualification.clause_access import SamplingStrategy
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.workflow import QualificationWorkflowPlanner, WorkflowStage

_RENDERER = CliWorkflowOperationRenderer()
BASE_MANIFEST = Path("manifests/applicability-presence-qualification-v1.yaml")


def _command(step) -> tuple[str, ...]:
    return _RENDERER.render(step.operation)


def _semantic_extraction_manifest(tmp_path: Path) -> Path:
    payload = yaml.safe_load(BASE_MANIFEST.read_text(encoding="utf-8"))
    payload["matrix_id"] = "applicability-presence-with-semantic-extraction-test"
    payload["dataset_version"] = "1.0.1"
    payload["semantic_extraction_qualification"] = {
        "enabled": True,
        "model": "mistral-small-3.2-24b-instruct-q4-k-m",
        "ontology_versions": [
            "standards-atlas-core@1.1.0",
            "functional-safety@1.1.0",
        ],
    }
    path = tmp_path / "qualification.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _plan(tmp_path: Path, *, fresh: bool = False, limit: int | None = 50):
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    return QualificationWorkflowPlanner().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        manifest_path=_semantic_extraction_manifest(tmp_path),
        corpus_count=500,
        limit=limit,
        corpus_strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        corpus_seed=20260818,
        knowledge_domain="functional-safety",
        overwrite=fresh,
        fresh=fresh,
    )


def test_current_manifest_contract_can_enable_semantic_extraction_qualification(
    tmp_path: Path,
) -> None:
    manifest = QualificationMatrixManifest.load(_semantic_extraction_manifest(tmp_path))
    assert manifest.semantic_extraction_qualification.enabled is True
    assert (
        manifest.semantic_extraction_qualification.model == "mistral-small-3.2-24b-instruct-q4-k-m"
    )
    assert (
        "standards-atlas-core@1.1.0" in manifest.semantic_extraction_qualification.ontology_versions
    )


def test_limit_is_propagated_to_semantic_extraction_qualification(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    extraction = next(
        step for step in plan.steps if step.stage is WorkflowStage.SEMANTIC_EXTRACTION_QUALIFICATION
    )

    assert _command(extraction)[_command(extraction).index("--limit") + 1] == "50"


def test_workflow_defers_archive_until_after_semantic_extraction(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    matrix = next(step for step in plan.steps if step.stage.value == "qualification-matrix")
    extraction = next(
        step for step in plan.steps if step.stage.value == "semantic-extraction-qualification"
    )
    archive = next(step for step in plan.steps if step.stage.value == "qualification-archive")
    assert "--no-create-archive" in _command(matrix)
    assert plan.steps.index(matrix) < plan.steps.index(extraction) < plan.steps.index(archive)
    assert _command(archive)[-2:] == ("--limit", "50")


def test_workflow_treats_semantic_extraction_failure_as_quality_result(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    extraction = next(
        step for step in plan.steps if step.stage is WorkflowStage.SEMANTIC_EXTRACTION_QUALIFICATION
    )

    assert "--no-fail-on-qualification-failure" in _command(extraction)


def test_fresh_is_propagated_to_matrix_and_semantic_extraction(tmp_path: Path) -> None:
    plan = _plan(tmp_path, fresh=True)
    matrix = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_MATRIX)
    extraction = next(
        step for step in plan.steps if step.stage is WorkflowStage.SEMANTIC_EXTRACTION_QUALIFICATION
    )

    assert "--overwrite" in _command(matrix)
    assert "--fresh" in _command(matrix)
    assert "--fresh" in _command(extraction)


def test_corpus_step_tracks_dataset_version_output(tmp_path: Path) -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    manifest_path = _semantic_extraction_manifest(tmp_path)
    manifest = QualificationMatrixManifest.load(manifest_path)
    plan = QualificationWorkflowPlanner().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        manifest_path=manifest_path,
        corpus_count=500,
        corpus_strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        corpus_seed=20260818,
        knowledge_domain="functional-safety",
    )
    corpus = next(step for step in plan.steps if step.stage is WorkflowStage.CORPUS_BUILD)

    assert any(
        f"/{manifest.task}/{manifest.dataset_version}/dataset.json" in path
        for path in corpus.output_paths
    )
    assert all(
        f"/{manifest.task}/{manifest.task_version}/dataset.json" not in path
        for path in corpus.output_paths
    )
