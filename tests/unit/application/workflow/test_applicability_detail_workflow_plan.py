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
    fresh_applicability_policy: bool = False,
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
        fresh_applicability_policy=fresh_applicability_policy,
        corpus_output=corpus_output,
    )


def test_v6_workflow_runs_applicability_policy_between_matrix_and_archive() -> None:
    plan = _plan()
    matrix = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_MATRIX)
    policy = next(
        step for step in plan.steps if step.stage is WorkflowStage.APPLICABILITY_DECISION_POLICY
    )
    archive = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_ARCHIVE)

    assert plan.steps.index(matrix) < plan.steps.index(policy) < plan.steps.index(archive)
    assert policy.command[:5] == (
        "uv",
        "run",
        "standards-atlas",
        "evaluation",
        "applicability-policy-run",
    )
    assert policy.command[policy.command.index("--manifest") + 1] == str(V6_MANIFEST)
    assert policy.command[policy.command.index("--run") + 1].endswith(
        "/multidimensional-semantic-qualification-v6-applicability-presence"
    )
    assert "--limit" not in policy.command
    assert any(
        path.endswith("/applicability-policy-selection.json") for path in policy.output_paths
    )
    assert any(
        path.endswith("/applicability-policy-run-state.json") for path in policy.output_paths
    )
    assert any(path.endswith("/applicability-policy-run.json") for path in policy.output_paths)
    assert any(
        path.endswith("/applicability-policy-evaluation.json") for path in policy.output_paths
    )
    assert any(path.endswith("/applicability-policy") for path in policy.output_paths)
    assert any(path.endswith("/applicability-policy.complete") for path in policy.output_paths)


def test_fresh_qualification_marks_policy_as_fresh_end_to_end() -> None:
    plan = _plan(fresh=True)
    policy = next(
        step for step in plan.steps if step.stage is WorkflowStage.APPLICABILITY_DECISION_POLICY
    )

    assert "--fresh" in policy.command
    assert policy.command[policy.command.index("--qualification-mode") + 1] == "fresh_end_to_end"
    assert plan.fresh_repetition_stages == (
        WorkflowStage.QUALIFICATION_MATRIX,
        WorkflowStage.APPLICABILITY_DECISION_POLICY,
    )


def test_fresh_policy_only_keeps_matrix_nonfresh() -> None:
    plan = _plan(fresh_applicability_policy=True)
    matrix = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_MATRIX)
    policy = next(
        step for step in plan.steps if step.stage is WorkflowStage.APPLICABILITY_DECISION_POLICY
    )

    assert "--fresh" not in matrix.command
    assert "--fresh" in policy.command
    assert (
        policy.command[policy.command.index("--qualification-mode") + 1]
        == "fresh_detail_fixed_presence"
    )
    assert plan.fresh_repetition_stages == (WorkflowStage.APPLICABILITY_DECISION_POLICY,)


def test_custom_corpus_root_is_shared_by_policy_and_archive_stages() -> None:
    corpus_root = Path("local/custom-corpora")
    plan = _plan(corpus_output=corpus_root)
    policy = next(
        step for step in plan.steps if step.stage is WorkflowStage.APPLICABILITY_DECISION_POLICY
    )
    archive = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_ARCHIVE)

    assert policy.command[policy.command.index("--corpus-root") + 1] == str(corpus_root)
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
    assert all(step.stage is not WorkflowStage.APPLICABILITY_DECISION_POLICY for step in plan.steps)
