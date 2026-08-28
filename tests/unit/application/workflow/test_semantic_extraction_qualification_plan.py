from pathlib import Path

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.application.semantic_qualification.clause_access import SamplingStrategy
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.workflow import QualificationWorkflowPlanner, WorkflowStage


def test_v5_manifest_enables_semantic_extraction_qualification() -> None:
    manifest = QualificationMatrixManifest.load(
        Path("manifests/multidimensional-semantic-qualification-v5-applicability-semantics-v1.yaml")
    )
    assert manifest.semantic_extraction_qualification.enabled is True
    assert (
        manifest.semantic_extraction_qualification.model == "mistral-small-3.2-24b-instruct-q4-k-m"
    )
    assert (
        "standards-atlas-core@1.1.0" in manifest.semantic_extraction_qualification.ontology_versions
    )


def test_v5_limit_is_propagated_to_semantic_extraction_qualification() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = QualificationWorkflowPlanner().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        manifest_path=Path(
            "manifests/multidimensional-semantic-qualification-v5-applicability-semantics-v1.yaml"
        ),
        corpus_count=500,
        limit=50,
        corpus_strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        corpus_seed=20260818,
        knowledge_domain="functional-safety",
    )
    extraction = next(
        step for step in plan.steps if step.stage is WorkflowStage.SEMANTIC_EXTRACTION_QUALIFICATION
    )

    assert extraction.command[extraction.command.index("--limit") + 1] == "50"


def test_v5_workflow_defers_archive_until_after_semantic_extraction() -> None:
    manifest_path = Path(
        "manifests/multidimensional-semantic-qualification-v5-applicability-semantics-v1.yaml"
    )
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = QualificationWorkflowPlanner().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        manifest_path=manifest_path,
        corpus_count=500,
        limit=50,
        corpus_strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        corpus_seed=20260818,
        knowledge_domain="functional-safety",
    )
    matrix = next(step for step in plan.steps if step.stage.value == "qualification-matrix")
    extraction = next(
        step for step in plan.steps if step.stage.value == "semantic-extraction-qualification"
    )
    archive = next(step for step in plan.steps if step.stage.value == "qualification-archive")
    assert "--no-create-archive" in matrix.command
    assert plan.steps.index(matrix) < plan.steps.index(extraction) < plan.steps.index(archive)
    assert archive.command[-2:] == ("--limit", "50")


def test_v5_workflow_treats_semantic_extraction_failure_as_quality_result() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = QualificationWorkflowPlanner().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        manifest_path=Path(
            "manifests/multidimensional-semantic-qualification-v5-applicability-semantics-v1.yaml"
        ),
        corpus_count=500,
        limit=50,
        corpus_strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        corpus_seed=20260818,
        knowledge_domain="functional-safety",
    )
    extraction = next(
        step for step in plan.steps if step.stage is WorkflowStage.SEMANTIC_EXTRACTION_QUALIFICATION
    )

    assert "--no-fail-on-qualification-failure" in extraction.command


def test_v5_fresh_is_propagated_to_matrix_and_semantic_extraction() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = QualificationWorkflowPlanner().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        manifest_path=Path(
            "manifests/multidimensional-semantic-qualification-v5-applicability-semantics-v1.yaml"
        ),
        corpus_count=500,
        limit=50,
        corpus_strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        corpus_seed=20260818,
        knowledge_domain="functional-safety",
        overwrite=True,
        fresh=True,
    )
    matrix = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_MATRIX)
    extraction = next(
        step for step in plan.steps if step.stage is WorkflowStage.SEMANTIC_EXTRACTION_QUALIFICATION
    )

    assert "--overwrite" in matrix.command
    assert "--fresh" in matrix.command
    assert "--fresh" in extraction.command


def test_corpus_step_tracks_dataset_version_output() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    manifest_path = Path(
        "manifests/multidimensional-semantic-qualification-v5-applicability-semantics-v1.yaml"
    )
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
