"""Planning for the document-to-qualification workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from standards_atlas.application.catalog import StandardCatalog
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    APPLICABILITY_DETAIL_ARTIFACT_DIRECTORY,
    APPLICABILITY_DETAIL_FAILURES_FILENAME,
    APPLICABILITY_DETAIL_REPORT_FILENAME,
    APPLICABILITY_DETAIL_SELECTION_FILENAME,
)
from standards_atlas.application.semantic_qualification.applicability_policy_qualification import (
    APPLICABILITY_POLICY_ARTIFACT_DIRECTORY,
    APPLICABILITY_POLICY_EVALUATION_FILENAME,
    APPLICABILITY_POLICY_RUN_FILENAME,
    APPLICABILITY_POLICY_SELECTION_FILENAME,
    APPLICABILITY_POLICY_STATE_FILENAME,
    ApplicabilityPolicyQualificationMode,
)
from standards_atlas.application.semantic_qualification.clause_access import SamplingStrategy
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QUALIFICATION_CORPUS_SNAPSHOT_FILENAME,
    QUALIFICATION_DATASET_SNAPSHOT_FILENAME,
    QUALIFICATION_SELECTION_FILENAME,
)
from standards_atlas.application.workflow.models import (
    ArtifactPolicy,
    WorkflowOperation,
    WorkflowOperationKind,
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
    fresh_repetition_stages: tuple[WorkflowStage, ...] = ()


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
        corpus_count: int | None,
        limit: int | None = None,
        corpus_strategy: SamplingStrategy,
        corpus_seed: int,
        knowledge_domain: str,
        hierarchy_key: str | None = None,
        regenerate_docling: bool = False,
        overwrite: bool = False,
        fresh: bool = False,
        fresh_applicability_policy: bool = False,
        keep_stages: tuple[WorkflowStage, ...] = (),
        qualification_output: Path = Path(".atlas/data/evaluation/qualification"),
        corpus_output: Path = Path(".atlas/data/evaluation/corpora"),
    ) -> QualificationWorkflowPlan:
        manifest = QualificationMatrixManifest.load(manifest_path)
        if fresh_applicability_policy and not manifest.applicability_decision_policy.enabled:
            raise ValueError(
                "--fresh-applicability-policy requires an enabled applicability decision policy"
            )
        document_plan = self._document_planner.plan(
            catalog,
            family_keys=family_keys,
            catalog_root=catalog_root,
            force=overwrite,
            keep_stages=keep_stages,
            hierarchy_key=hierarchy_key,
            include_semantic_enrichment=True,
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
            operation=WorkflowOperation.create(
                WorkflowOperationKind.EVALUATION_CORPUS_BUILD,
                task=manifest.task,
                version=manifest.dataset_version,
                corpus_id=manifest.corpus_id,
                knowledge_domain=knowledge_domain,
                count=corpus_count,
                all_clauses=corpus_count is None,
                strategy=corpus_strategy.value,
                seed=corpus_seed,
                output=str(corpus_output),
            ),
            artifact_policy=ArtifactPolicy.DERIVED,
            output_paths=(
                str(corpus_output / manifest.task / manifest.dataset_version / "dataset.json"),
                str(corpus_output / manifest.corpus_id / "corpus.yaml"),
            ),
        )
        matrix_step = WorkflowStep(
            family="evaluation",
            document=manifest.matrix_id,
            stage=WorkflowStage.QUALIFICATION_MATRIX,
            operation=WorkflowOperation.create(
                WorkflowOperationKind.EVALUATION_QUALIFICATION_MATRIX,
                manifest=str(manifest_path),
                output=str(qualification_output),
                continue_on_matrix_failure=True,
                limit=limit,
                corpus_root=str(corpus_output),
                skip_archive_creation=True,
                overwrite=overwrite,
                fresh=fresh,
            ),
            artifact_policy=ArtifactPolicy.DERIVED,
            output_paths=(
                str(qualification_output / manifest.matrix_id),
                str(qualification_output / manifest.matrix_id / QUALIFICATION_SELECTION_FILENAME),
                str(
                    qualification_output
                    / manifest.matrix_id
                    / QUALIFICATION_DATASET_SNAPSHOT_FILENAME
                ),
                str(
                    qualification_output
                    / manifest.matrix_id
                    / QUALIFICATION_CORPUS_SNAPSHOT_FILENAME
                ),
                f".atlas/work/workflow/qualification/{manifest.matrix_id}/matrix.complete",
            ),
        )
        steps: tuple[WorkflowStep, ...] = (*document_steps, corpus_step, matrix_step)
        detail_config = manifest.applicability_detail_enrichment
        policy_config = manifest.applicability_decision_policy
        if policy_config.enabled:
            policy_output = (
                qualification_output / manifest.matrix_id / APPLICABILITY_POLICY_ARTIFACT_DIRECTORY
            )
            policy_mode = None
            if fresh or fresh_applicability_policy:
                policy_mode = (
                    ApplicabilityPolicyQualificationMode.FRESH_END_TO_END
                    if fresh
                    else ApplicabilityPolicyQualificationMode.FRESH_DETAIL_FIXED_PRESENCE
                ).value
            policy_operation = WorkflowOperation.create(
                WorkflowOperationKind.EVALUATION_APPLICABILITY_POLICY,
                manifest=str(manifest_path),
                run=str(qualification_output / manifest.matrix_id),
                corpus_root=str(corpus_output),
                output_directory=str(policy_output),
                fresh=fresh or fresh_applicability_policy,
                qualification_mode=policy_mode,
            )
            policy_outputs = [
                str(policy_output / APPLICABILITY_POLICY_SELECTION_FILENAME),
                str(policy_output / APPLICABILITY_POLICY_STATE_FILENAME),
                str(policy_output / APPLICABILITY_POLICY_RUN_FILENAME),
            ]
            if policy_config.golden_corpus is not None:
                policy_outputs.append(str(policy_output / APPLICABILITY_POLICY_EVALUATION_FILENAME))
            policy_outputs.extend(
                (
                    str(policy_output),
                    (
                        ".atlas/work/workflow/qualification/"
                        f"{manifest.matrix_id}/applicability-policy.complete"
                    ),
                )
            )
            policy_step = WorkflowStep(
                family="evaluation",
                document=f"{manifest.matrix_id}-applicability-policy",
                stage=WorkflowStage.APPLICABILITY_DECISION_POLICY,
                operation=policy_operation,
                artifact_policy=ArtifactPolicy.DERIVED,
                output_paths=tuple(policy_outputs),
            )
            steps = (*steps, policy_step)
        elif detail_config.enabled:
            detail_operation = WorkflowOperation.create(
                WorkflowOperationKind.EVALUATION_APPLICABILITY_DETAIL,
                manifest=str(manifest_path),
                run=str(qualification_output / manifest.matrix_id),
                corpus_root=str(corpus_output),
                fresh=fresh or fresh_applicability_policy,
            )
            detail_step = WorkflowStep(
                family="evaluation",
                document=f"{manifest.matrix_id}-applicability-detail",
                stage=WorkflowStage.APPLICABILITY_DETAIL_ENRICHMENT,
                operation=detail_operation,
                artifact_policy=ArtifactPolicy.DERIVED,
                output_paths=(
                    str(
                        qualification_output
                        / manifest.matrix_id
                        / APPLICABILITY_DETAIL_SELECTION_FILENAME
                    ),
                    str(
                        qualification_output
                        / manifest.matrix_id
                        / APPLICABILITY_DETAIL_REPORT_FILENAME
                    ),
                    str(
                        qualification_output
                        / manifest.matrix_id
                        / APPLICABILITY_DETAIL_FAILURES_FILENAME
                    ),
                    str(
                        qualification_output
                        / manifest.matrix_id
                        / APPLICABILITY_DETAIL_ARTIFACT_DIRECTORY
                    ),
                    (
                        ".atlas/work/workflow/qualification/"
                        f"{manifest.matrix_id}/applicability-detail.complete"
                    ),
                ),
            )
            steps = (*steps, detail_step)
        archive_operation = WorkflowOperation.create(
            WorkflowOperationKind.EVALUATION_QUALIFICATION_ARCHIVE,
            manifest=str(manifest_path),
            output=str(qualification_output),
            corpus_root=str(corpus_output),
            limit=limit,
        )
        archive_step = WorkflowStep(
            family="evaluation",
            document=f"{manifest.matrix_id}-archive",
            stage=WorkflowStage.QUALIFICATION_ARCHIVE,
            operation=archive_operation,
            artifact_policy=ArtifactPolicy.REVIEW,
            output_paths=("local/evaluation/qualification-run-*.zip",),
        )
        steps = (*steps, archive_step)
        fresh_repetition_stages: list[WorkflowStage] = []
        if fresh:
            fresh_repetition_stages.append(WorkflowStage.QUALIFICATION_MATRIX)
            if policy_config.enabled:
                fresh_repetition_stages.append(WorkflowStage.APPLICABILITY_DECISION_POLICY)
            elif detail_config.enabled:
                fresh_repetition_stages.append(WorkflowStage.APPLICABILITY_DETAIL_ENRICHMENT)
        elif fresh_applicability_policy:
            fresh_repetition_stages.append(WorkflowStage.APPLICABILITY_DECISION_POLICY)
        return QualificationWorkflowPlan(
            document_plan=document_plan,
            steps=steps,
            fresh_repetition_stages=tuple(fresh_repetition_stages),
        )

    @staticmethod
    def _docling_policy(step: WorkflowStep, regenerate: bool) -> WorkflowStep:
        if step.stage is not WorkflowStage.DOCLING or not regenerate:
            return step
        return WorkflowStep(
            family=step.family,
            document=step.document,
            stage=step.stage,
            operation=step.operation.with_parameters(overwrite=True),
            artifact_policy=step.artifact_policy,
            manual_gate=step.manual_gate,
            output_paths=step.output_paths,
            output_globs=step.output_globs,
        )
