from pathlib import Path

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.application.semantic_qualification.clause_access import SamplingStrategy
from standards_atlas.application.workflow import (
    RoutedQualificationWorkflowPlanner,
    WorkflowStage,
)

SUITE_MANIFEST = Path("manifests/multidimensional-semantic-qualification-v4-routed-suite-v1.yaml")


def _plan(*, overwrite: bool = False):
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    hierarchy = catalog.doorstop_hierarchy("functional-safety")
    return RoutedQualificationWorkflowPlanner().plan(
        catalog,
        family_keys=hierarchy.families,
        catalog_root=Path.cwd(),
        suite_manifest_path=SUITE_MANIFEST,
        corpus_count=500,
        corpus_strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        corpus_seed=20260818,
        knowledge_domain="functional-safety",
        hierarchy_key="functional-safety",
        overwrite=overwrite,
    )


def test_routed_qualification_runs_taxonomy_and_routing_before_evaluation() -> None:
    plan = _plan()
    stages = tuple(step.stage for step in plan.steps)

    assert WorkflowStage.TAXONOMY in stages
    assert WorkflowStage.ROUTING in stages
    assert stages.index(WorkflowStage.TAXONOMY) < stages.index(WorkflowStage.ROUTING)
    assert WorkflowStage.ONTOLOGY not in stages
    assert stages.index(WorkflowStage.ROUTING) < stages.index(WorkflowStage.CORPUS_BUILD)


def test_routed_qualification_plans_all_five_split_tasks_in_suite_order() -> None:
    plan = _plan()
    corpus_steps = [step for step in plan.steps if step.stage is WorkflowStage.CORPUS_BUILD]
    matrix_steps = [step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_MATRIX]

    assert len(corpus_steps) == 5
    assert len(matrix_steps) == 5
    assert [step.document for step in matrix_steps] == [
        "statement-function-qualification-v1",
        "knowledge-kind-qualification-v1",
        "process-function-qualification-v1",
        "applicability-qualification-v1",
        "role-relation-qualification-v1",
    ]
    assert all("--manifest" in step.command for step in matrix_steps)


def test_routed_qualification_overwrite_recomputes_all_matrices() -> None:
    plan = _plan(overwrite=True)
    matrix_steps = [step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_MATRIX]

    assert matrix_steps
    assert all(step.command[-1] == "--overwrite" for step in matrix_steps)


def test_routed_qualification_suite_selects_current_routing_contract() -> None:
    plan = _plan()

    assert plan.suite.suite_id == "multidimensional-semantic-qualification-v4-routed"
    routing_steps = [step for step in plan.steps if step.stage is WorkflowStage.ROUTING]
    assert routing_steps
    assert all(
        "manifests/functional-safety-semantic-routing-v1.yaml" in " ".join(step.command)
        for step in routing_steps
    )


def test_routed_qualification_corpus_versions_match_split_task_versions() -> None:
    plan = _plan()
    corpus_steps = [step for step in plan.steps if step.stage is WorkflowStage.CORPUS_BUILD]

    assert [step.output_paths[0] for step in corpus_steps] == [
        ".atlas/data/evaluation/corpora/statement-function-classification/3.0.0/dataset.json",
        ".atlas/data/evaluation/corpora/knowledge-kind-classification/1.0.0/dataset.json",
        ".atlas/data/evaluation/corpora/process-function-classification/1.0.0/dataset.json",
        ".atlas/data/evaluation/corpora/applicability-extraction/1.0.0/dataset.json",
        ".atlas/data/evaluation/corpora/role-relation-extraction/1.0.0/dataset.json",
    ]


def test_routed_qualification_rejects_dataset_task_version_drift() -> None:
    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        QualificationMatrixManifest,
    )

    names = (
        "statement-function",
        "knowledge-kind",
        "process-function",
        "applicability",
        "role-relation",
    )
    manifests = tuple(
        QualificationMatrixManifest.load(
            Path(f"manifests/multidimensional-semantic-qualification-v4-{name}-v1.yaml")
        )
        for name in names
    )
    drifted = (
        manifests[0].model_copy(update={"dataset_version": "2.2.0"}),
        *manifests[1:],
    )

    try:
        RoutedQualificationWorkflowPlanner._validate_suite(
            "functional-safety-semantic-profile",
            "1.1.0",
            drifted,
        )
    except ValueError as exc:
        assert "dataset_version" in str(exc)
        assert "task_version" in str(exc)
    else:
        raise AssertionError("expected routed qualification to reject version drift")
