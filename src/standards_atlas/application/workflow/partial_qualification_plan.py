"""Opt-in final qualification campaign through the existing qualification task."""

from pathlib import Path

from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    QualificationCampaign,
)
from standards_atlas.application.workflow.models import (
    ArtifactPolicy,
    WorkflowOperation,
    WorkflowOperationKind,
    WorkflowPlan,
    WorkflowStage,
    WorkflowStep,
)


def plan_partial_qualification(manifest: Path, output: Path) -> WorkflowPlan:
    spec = QualificationCampaign.load(manifest)
    root = output / spec.id
    review_steps = ()
    if spec.review_bundle is not None:
        review_steps = (
            WorkflowStep(
                family="evaluation",
                document=spec.id,
                stage=WorkflowStage.REVIEW,
                operation=WorkflowOperation.create(
                    WorkflowOperationKind.PARTIAL_REVIEW_CHECK_HANDOFF,
                    bundle=str(spec.review_bundle),
                ),
                artifact_policy=ArtifactPolicy.REVIEW,
            ),
        )
    return WorkflowPlan(
        families=("evaluation",),
        steps=(
            *review_steps,
            WorkflowStep(
                family="evaluation",
                document=spec.id,
                stage=WorkflowStage.CORPUS_BUILD,
                operation=WorkflowOperation.create(
                    WorkflowOperationKind.PARTIAL_QUALIFICATION_PREPARE,
                    manifest=str(manifest),
                    output=str(root),
                    reuse_frozen=True,
                ),
                artifact_policy=ArtifactPolicy.DERIVED,
            ),
            WorkflowStep(
                family="evaluation",
                document=spec.id,
                stage=WorkflowStage.QUALIFICATION_MATRIX,
                operation=WorkflowOperation.create(
                    WorkflowOperationKind.PARTIAL_QUALIFICATION_RUN,
                    campaign=str(root),
                    execute=True,
                ),
                artifact_policy=ArtifactPolicy.DERIVED,
            ),
            WorkflowStep(
                family="evaluation",
                document=spec.id,
                stage=WorkflowStage.QUALIFICATION_ARCHIVE,
                operation=WorkflowOperation.create(
                    WorkflowOperationKind.PARTIAL_QUALIFICATION_EVALUATE,
                    campaign=str(root),
                    archive_output=str(output / "archives"),
                ),
                artifact_policy=ArtifactPolicy.DERIVED,
            ),
        ),
    )
