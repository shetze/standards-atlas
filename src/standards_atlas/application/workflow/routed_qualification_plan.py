"""Planning for the taxonomy-routed multi-task qualification workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from standards_atlas.application.catalog import StandardCatalog
from standards_atlas.application.routing.manifest import load_routing_contract_manifest
from standards_atlas.application.semantic_qualification.clause_access import SamplingStrategy
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.workflow.models import (
    ArtifactPolicy,
    WorkflowPlan,
    WorkflowStage,
    WorkflowStep,
)
from standards_atlas.application.workflow.planner import WorkflowPlanner
from standards_atlas.application.workflow.qualification_plan import QualificationWorkflowPlanner
from standards_atlas.application.workflow.qualification_suite import (
    QualificationSuiteManifest,
    load_qualification_suite_manifest,
)


@dataclass(frozen=True)
class RoutedQualificationWorkflowPlan:
    """Plan from structural preprocessing through all routed qualification tasks."""

    document_plan: WorkflowPlan
    steps: tuple[WorkflowStep, ...]
    suite: QualificationSuiteManifest


class RoutedQualificationWorkflowPlanner:
    """Compose taxonomy/routing preprocessing with an ordered qualification suite."""

    def __init__(self, document_planner: WorkflowPlanner | None = None) -> None:
        self._document_planner = document_planner or WorkflowPlanner()

    def plan(
        self,
        catalog: StandardCatalog,
        *,
        family_keys: tuple[str, ...],
        catalog_root: Path,
        suite_manifest_path: Path,
        corpus_count: int,
        corpus_strategy: SamplingStrategy,
        corpus_seed: int,
        knowledge_domain: str,
        hierarchy_key: str | None = None,
        regenerate_docling: bool = False,
        overwrite: bool = False,
        keep_stages: tuple[WorkflowStage, ...] = (),
        qualification_output: Path = Path(".atlas/data/evaluation/qualification"),
        corpus_output: Path = Path(".atlas/data/evaluation/corpora"),
    ) -> RoutedQualificationWorkflowPlan:
        suite = load_qualification_suite_manifest(suite_manifest_path)
        routing_path, matrix_paths = suite.resolve(suite_manifest_path, catalog_root)
        if not routing_path.is_file():
            raise ValueError(f"qualification suite routing manifest does not exist: {routing_path}")
        missing = [path for path in matrix_paths if not path.is_file()]
        if missing:
            raise ValueError(
                "qualification suite matrix manifest does not exist: "
                + ", ".join(map(str, missing))
            )

        routing_manifest = load_routing_contract_manifest(routing_path)
        matrices = tuple(QualificationMatrixManifest.load(path) for path in matrix_paths)
        self._validate_suite(
            routing_manifest.contract.id,
            routing_manifest.contract.version,
            matrices,
        )

        document_plan = self._document_planner.plan(
            catalog,
            family_keys=family_keys,
            catalog_root=catalog_root,
            force=overwrite,
            keep_stages=keep_stages,
            hierarchy_key=hierarchy_key,
            routing_manifest_path=routing_path,
        )
        excluded_document_stages = {
            WorkflowStage.ONTOLOGY,
            WorkflowStage.DOORSTOP,
            WorkflowStage.DOORSTOP_PUBLISH,
        }
        document_steps = tuple(
            QualificationWorkflowPlanner._docling_policy(step, regenerate_docling)
            for step in document_plan.steps
            if step.stage not in excluded_document_stages
            and (regenerate_docling or step.stage is not WorkflowStage.DOCLING)
        )

        evaluation_steps: list[WorkflowStep] = []
        for manifest_path, manifest in zip(matrix_paths, matrices, strict=True):
            corpus_step = WorkflowStep(
                family="evaluation",
                document=f"{suite.suite_id}:{manifest.task}",
                stage=WorkflowStage.CORPUS_BUILD,
                command=(
                    "uv",
                    "run",
                    "standards-atlas",
                    "evaluation",
                    "corpus-build",
                    "--task",
                    manifest.task,
                    "--version",
                    manifest.task_version,
                    "--corpus-id",
                    manifest.corpus_id,
                    "--knowledge-domain",
                    knowledge_domain,
                    "--count",
                    str(corpus_count),
                    "--strategy",
                    corpus_strategy.value,
                    "--seed",
                    str(corpus_seed),
                    "--output",
                    str(corpus_output),
                ),
                artifact_policy=ArtifactPolicy.DERIVED,
                output_paths=(
                    str(corpus_output / manifest.task / manifest.task_version / "dataset.json"),
                ),
            )
            matrix_command = [
                "uv",
                "run",
                "standards-atlas",
                "evaluation",
                "qualification-matrix",
                "--manifest",
                str(manifest_path),
                "--output",
                str(qualification_output),
                "--routing-manifest",
                str(routing_path),
                "--suite-manifest",
                str(suite_manifest_path),
                "--no-fail-on-matrix-failure",
            ]
            if overwrite:
                matrix_command.append("--overwrite")
            matrix_step = WorkflowStep(
                family="evaluation",
                document=manifest.matrix_id,
                stage=WorkflowStage.QUALIFICATION_MATRIX,
                command=tuple(matrix_command),
                artifact_policy=ArtifactPolicy.DERIVED,
                output_paths=(str(qualification_output / manifest.matrix_id),),
            )
            evaluation_steps.extend((corpus_step, matrix_step))

        return RoutedQualificationWorkflowPlan(
            document_plan=document_plan,
            steps=(*document_steps, *evaluation_steps),
            suite=suite,
        )

    @staticmethod
    def _validate_suite(contract_id: str, contract_version: str, matrices) -> None:
        expected_tasks = {
            "statement-function-classification",
            "knowledge-kind-classification",
            "process-function-classification",
            "applicability-extraction",
            "role-relation-extraction",
        }
        actual_tasks = {manifest.task for manifest in matrices}
        if actual_tasks != expected_tasks:
            missing = sorted(expected_tasks - actual_tasks)
            extra = sorted(actual_tasks - expected_tasks)
            raise ValueError(
                "routed qualification suite must contain exactly the five split semantic tasks; "
                f"missing={missing}, extra={extra}"
            )
        for manifest in matrices:
            routing = manifest.routing
            if routing is None:
                raise ValueError(
                    f"qualification manifest {manifest.matrix_id!r} has no routing policy"
                )
            if routing.contract_id != contract_id or routing.contract_version != contract_version:
                raise ValueError(
                    f"qualification manifest {manifest.matrix_id!r} expects routing contract "
                    f"{routing.contract_id}@{routing.contract_version}, but suite selects "
                    f"{contract_id}@{contract_version}"
                )
