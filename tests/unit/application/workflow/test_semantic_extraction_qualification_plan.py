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
