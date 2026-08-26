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
        limit: int | None = None,
        corpus_strategy: SamplingStrategy,
        corpus_seed: int,
        knowledge_domain: str,
        hierarchy_key: str | None = None,
        regenerate_docling: bool = False,
        overwrite: bool = False,
        fresh: bool = False,
        keep_stages: tuple[WorkflowStage, ...] = (),
        qualification_output: Path = Path(".atlas/data/evaluation/qualification"),
        corpus_output: Path = Path(".atlas/data/evaluation/corpora"),
    ) -> QualificationWorkflowPlan:
        manifest = QualificationMatrixManifest.load(manifest_path)
        document_plan = self._document_planner.plan(
            catalog,
            family_keys=family_keys,
            catalog_root=catalog_root,
            force=overwrite,
            keep_stages=keep_stages,
            hierarchy_key=hierarchy_key,
            include_semantic_profile=True,
        )
        excluded_document_stages = {
            WorkflowStage.DOORSTOP,
            WorkflowStage.DOORSTOP_PUBLISH,
        }
        document_steps = tuple(
            self._docling_policy(step, regenerate_docling)
            for step in document_plan.steps
            if step.stage not in excluded_document_stages
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
        if limit is not None:
            matrix_command.extend(("--limit", str(limit)))
        matrix_command.append("--no-create-archive")
        if overwrite:
            matrix_command.append("--overwrite")
        if fresh:
            matrix_command.append("--fresh")
        matrix_step = WorkflowStep(
            family="evaluation",
            document=manifest.matrix_id,
            stage=WorkflowStage.QUALIFICATION_MATRIX,
            command=tuple(matrix_command),
            artifact_policy=ArtifactPolicy.DERIVED,
            output_paths=(str(qualification_output / manifest.matrix_id),),
        )
        steps: tuple[WorkflowStep, ...] = (*document_steps, corpus_step, matrix_step)
        extraction_config = manifest.semantic_extraction_qualification
        if extraction_config.enabled:
            extraction_command = [
                "uv",
                "run",
                "standards-atlas",
                "evaluation",
                "semantic-extraction-qualification",
                "--manifest",
                str(manifest_path),
                "--output",
                str(qualification_output / manifest.matrix_id),
                "--no-fail-on-qualification-failure",
            ]
            if limit is not None:
                extraction_command.extend(("--limit", str(limit)))
            if fresh:
                extraction_command.append("--fresh")
            extraction_step = WorkflowStep(
                family="evaluation",
                document=f"{manifest.matrix_id}-semantic-extraction",
                stage=WorkflowStage.SEMANTIC_EXTRACTION_QUALIFICATION,
                command=tuple(extraction_command),
                artifact_policy=ArtifactPolicy.DERIVED,
                output_paths=(
                    str(
                        qualification_output
                        / manifest.matrix_id
                        / "semantic-extraction-qualification.json"
                    ),
                ),
            )
            steps = (*steps, extraction_step)
        archive_command = [
            "uv",
            "run",
            "standards-atlas",
            "evaluation",
            "qualification-archive",
            "--manifest",
            str(manifest_path),
            "--output",
            str(qualification_output),
        ]
        if limit is not None:
            archive_command.extend(("--limit", str(limit)))
        archive_step = WorkflowStep(
            family="evaluation",
            document=f"{manifest.matrix_id}-archive",
            stage=WorkflowStage.QUALIFICATION_ARCHIVE,
            command=tuple(archive_command),
            artifact_policy=ArtifactPolicy.REVIEW,
            output_paths=("local/evaluation/qualification-run-*.zip",),
        )
        steps = (*steps, archive_step)
        return QualificationWorkflowPlan(
            document_plan=document_plan,
            steps=steps,
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
