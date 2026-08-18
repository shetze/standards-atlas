"""Planning for the document-to-qualification workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from standards_atlas.application.catalog import StandardCatalog
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


@dataclass(frozen=True)
class QualificationWorkflowPlan:
    """Reproducible plan from document extraction through qualification."""

    document_plan: WorkflowPlan
    steps: tuple[WorkflowStep, ...]


class QualificationWorkflowPlanner:
    """Compose the existing document workflow with corpus and matrix evaluation."""

    def __init__(self, document_planner: WorkflowPlanner | None = None) -> None:
        self._document_planner = document_planner or WorkflowPlanner()

    def plan(
        self,
        catalog: StandardCatalog,
        *,
        family_keys: tuple[str, ...],
        catalog_root: Path,
        manifest_path: Path,
        corpus_count: int,
        corpus_strategy: SamplingStrategy,
        corpus_seed: int,
        knowledge_domain: str,
        hierarchy_key: str | None = None,
        regenerate_docling: bool = False,
        overwrite: bool = False,
        keep_stages: tuple[WorkflowStage, ...] = (),
        qualification_output: Path = Path("local/evaluation/qualification"),
        corpus_output: Path = Path("local/evaluation/corpora"),
    ) -> QualificationWorkflowPlan:
        manifest = QualificationMatrixManifest.load(manifest_path)
        document_plan = self._document_planner.plan(
            catalog,
            family_keys=family_keys,
            catalog_root=catalog_root,
            force=overwrite,
            keep_stages=keep_stages,
            hierarchy_key=hierarchy_key,
        )
        document_steps = tuple(
            self._docling_policy(step, regenerate_docling)
            for step in document_plan.steps
            if step.stage not in {WorkflowStage.DOORSTOP, WorkflowStage.DOORSTOP_PUBLISH}
            and (regenerate_docling or step.stage is not WorkflowStage.DOCLING)
        )
        corpus_step = WorkflowStep(
            family="evaluation",
            document=manifest.corpus_id,
            stage=WorkflowStage.CORPUS_BUILD,
            command=(
                "uv",
                "run",
                "standards-atlas",
                "evaluation",
                "corpus-build",
                "--task",
                "statement-function-classification",
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
                str(
                    corpus_output
                    / "statement-function-classification"
                    / manifest.task_version
                    / "dataset.json"
                ),
                str(corpus_output / manifest.corpus_id / "corpus.yaml"),
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
        return QualificationWorkflowPlan(
            document_plan=document_plan,
            steps=(*document_steps, corpus_step, matrix_step),
        )

    @staticmethod
    def _docling_policy(step: WorkflowStep, regenerate: bool) -> WorkflowStep:
        if step.stage is not WorkflowStage.DOCLING or not regenerate:
            return step
        command = step.command if "--overwrite" in step.command else (*step.command, "--overwrite")
        return WorkflowStep(
            family=step.family,
            document=step.document,
            stage=step.stage,
            command=command,
            artifact_policy=step.artifact_policy,
            manual_gate=step.manual_gate,
            output_paths=step.output_paths,
            output_globs=step.output_globs,
        )
