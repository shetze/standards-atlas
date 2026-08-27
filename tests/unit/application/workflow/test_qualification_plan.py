from pathlib import Path

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.application.semantic_qualification.clause_access import SamplingStrategy
from standards_atlas.application.workflow import QualificationWorkflowPlanner, WorkflowStage

QUALIFICATION_MANIFEST = Path(
    "manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml"
)


def _plan(*, regenerate_docling: bool = False, overwrite: bool = False, limit: int | None = None):
    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    return QualificationWorkflowPlanner().plan(
        catalog,
        family_keys=("EN50716",),
        catalog_root=Path.cwd(),
        manifest_path=QUALIFICATION_MANIFEST,
        corpus_count=500,
        limit=limit,
        corpus_strategy=SamplingStrategy.REPRESENTATIVE_STRATIFIED,
        corpus_seed=20260818,
        knowledge_domain="functional-safety",
        regenerate_docling=regenerate_docling,
        overwrite=overwrite,
    )


def test_qualification_plan_stops_document_pipeline_at_markdown() -> None:
    plan = _plan()
    stages = tuple(step.stage for step in plan.steps)

    assert WorkflowStage.MARKDOWN in stages
    assert WorkflowStage.DOORSTOP not in stages
    assert WorkflowStage.DOORSTOP_PUBLISH not in stages
    assert stages[-3:] == (
        WorkflowStage.CORPUS_BUILD,
        WorkflowStage.QUALIFICATION_MATRIX,
        WorkflowStage.QUALIFICATION_ARCHIVE,
    )


def test_qualification_plan_requires_taxonomy_and_semantic_profile_classification() -> None:
    plan = _plan()
    stages = tuple(step.stage for step in plan.steps)

    assert WorkflowStage.TAXONOMY in stages
    assert WorkflowStage.SEMANTIC_CLASSIFICATION in stages
    assert any("classify-semantics" in step.command for step in plan.steps)


def test_qualification_plan_derives_corpus_contract_from_matrix_manifest() -> None:
    plan = _plan()
    corpus = next(step for step in plan.steps if step.stage is WorkflowStage.CORPUS_BUILD)

    assert "--version" in corpus.command
    assert corpus.command[corpus.command.index("--version") + 1] == "2.2.0"
    assert corpus.command[corpus.command.index("--corpus-id") + 1] == "semantic-profile-v1"
    assert corpus.command[corpus.command.index("--strategy") + 1] == "representative_stratified"
    assert corpus.command[corpus.command.index("--seed") + 1] == "20260818"


def test_docling_is_reused_unless_regeneration_is_requested() -> None:
    normal = _plan()
    regenerated = _plan(regenerate_docling=True, overwrite=True)

    assert all(step.stage is not WorkflowStage.DOCLING for step in normal.steps)
    regenerated_docling = next(
        step for step in regenerated.steps if step.stage is WorkflowStage.DOCLING
    )
    assert regenerated_docling.command[-1] == "--overwrite"


def test_overwrite_propagates_to_derived_document_and_matrix_steps() -> None:
    plan = _plan(overwrite=True)
    matrix = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_MATRIX)

    assert "--no-fail-on-matrix-failure" in matrix.command
    assert matrix.command[-1] == "--overwrite"
    assert any(
        step.stage is WorkflowStage.NORMALIZE and "--overwrite" in step.command
        for step in plan.steps
    )


def test_limit_is_forwarded_to_all_qualification_stages() -> None:
    plan = _plan(limit=50)

    matrix = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_MATRIX)
    assert matrix.command[matrix.command.index("--limit") + 1] == "50"

    extraction_steps = tuple(
        step for step in plan.steps if step.stage is WorkflowStage.SEMANTIC_EXTRACTION_QUALIFICATION
    )
    for extraction in extraction_steps:
        assert extraction.command[extraction.command.index("--limit") + 1] == "50"

    archive = next(step for step in plan.steps if step.stage is WorkflowStage.QUALIFICATION_ARCHIVE)
    assert archive.command[archive.command.index("--limit") + 1] == "50"


def test_corpus_build_uses_dataset_version_when_task_version_differs() -> None:
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
    corpus = next(step for step in plan.steps if step.stage is WorkflowStage.CORPUS_BUILD)

    assert corpus.command[corpus.command.index("--version") + 1] == "2.2.0"
