from pathlib import Path

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.application.semantic_qualification.clause_access import SamplingStrategy
from standards_atlas.application.workflow import QualificationWorkflowPlanner, WorkflowStage

V6_MANIFEST = Path(
    "manifests/multidimensional-semantic-qualification-v6-applicability-presence-v1.yaml"
)


def _plan(
    *,
    fresh: bool = False,
    corpus_output: Path = Path(".atlas/data/evaluation/corpora"),
):
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    return QualificationWorkflowPlanner().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        manifest_path=V6_MANIFEST,
        corpus_count=500,
        limit=50,
        corpus_strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        corpus_seed=20260818,
        knowledge_domain="functional-safety",
        overwrite=fresh,
        fresh=fresh,
        corpus_output=corpus_output,
    )


def test_v6_workflow_runs_sparse_detail_enrichment_between_matrix_and_archive() -> None:
    plan = _plan()
    matrix = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_MATRIX)
    detail = next(
        step for step in plan.steps if step.stage is WorkflowStage.APPLICABILITY_DETAIL_ENRICHMENT
    )
    archive = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_ARCHIVE)

    assert plan.steps.index(matrix) < plan.steps.index(detail) < plan.steps.index(archive)
    assert detail.command[:5] == (
        "uv",
        "run",
        "standards-atlas",
        "evaluation",
        "applicability-detail-enrich",
    )
    assert detail.command[detail.command.index("--manifest") + 1] == str(V6_MANIFEST)
    assert detail.command[detail.command.index("--run") + 1].endswith(
        "/multidimensional-semantic-qualification-v6-applicability-presence"
    )
    assert "--limit" not in detail.command
    assert any(
        path.endswith("/applicability-detail-selection.json") for path in detail.output_paths
    )
    assert any(
        path.endswith("/applicability-detail-enrichment.json") for path in detail.output_paths
    )
    assert any(path.endswith("/applicability-detail-failures.json") for path in detail.output_paths)
    assert any(path.endswith("/applicability-detail") for path in detail.output_paths)
    assert any(path.endswith("/applicability-detail.complete") for path in detail.output_paths)


def test_fresh_qualification_propagates_to_sparse_detail_enrichment() -> None:
    plan = _plan(fresh=True)
    detail = next(
        step for step in plan.steps if step.stage is WorkflowStage.APPLICABILITY_DETAIL_ENRICHMENT
    )

    assert detail.command[-1] == "--fresh"


def test_custom_corpus_root_is_shared_by_detail_and_archive_stages() -> None:
    corpus_root = Path("local/custom-corpora")
    plan = _plan(corpus_output=corpus_root)
    detail = next(
        step for step in plan.steps if step.stage is WorkflowStage.APPLICABILITY_DETAIL_ENRICHMENT
    )
    archive = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_ARCHIVE)

    assert detail.command[detail.command.index("--corpus-root") + 1] == str(corpus_root)
    assert archive.command[archive.command.index("--corpus-root") + 1] == str(corpus_root)


def test_manifests_without_detail_policy_keep_the_existing_workflow_shape() -> None:
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    plan = QualificationWorkflowPlanner().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        manifest_path=Path(
            "manifests/multidimensional-semantic-qualification-v5-applicability-semantics-v1.yaml"
        ),
        corpus_count=500,
        corpus_strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        corpus_seed=20260818,
        knowledge_domain="functional-safety",
    )

    assert all(
        step.stage is not WorkflowStage.APPLICABILITY_DETAIL_ENRICHMENT for step in plan.steps
    )
