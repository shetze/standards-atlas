"""Opt-in final qualification campaign through the existing qualification task."""

from pathlib import Path

from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    QualificationCampaign,
)
from standards_atlas.application.workflow.models import (
    ArtifactPolicy,
    WorkflowPlan,
    WorkflowStage,
    WorkflowStep,
)


def plan_partial_qualification(manifest: Path, output: Path) -> WorkflowPlan:
    spec = QualificationCampaign.load(manifest)
    root = output / spec.id
    prefix = ("uv", "run", "standards-atlas", "evaluation")
    return WorkflowPlan(
        families=("evaluation",),
        steps=(
            WorkflowStep(
                family="evaluation",
                document=spec.id,
                stage=WorkflowStage.CORPUS_BUILD,
                command=(
                    *prefix,
                    "partial-qualification-prepare",
                    "--manifest",
                    str(manifest),
                    "--output",
                    str(root),
                    "--reuse-frozen",
                ),
                artifact_policy=ArtifactPolicy.DERIVED,
            ),
            WorkflowStep(
                family="evaluation",
                document=spec.id,
                stage=WorkflowStage.QUALIFICATION_MATRIX,
                command=(
                    *prefix,
                    "partial-qualification-run",
                    "--campaign",
                    str(root),
                    "--execute",
                ),
                artifact_policy=ArtifactPolicy.DERIVED,
            ),
            WorkflowStep(
                family="evaluation",
                document=spec.id,
                stage=WorkflowStage.QUALIFICATION_ARCHIVE,
                command=(
                    *prefix,
                    "partial-qualification-evaluate",
                    "--campaign",
                    str(root),
                    "--archive-output",
                    str(output / "archives"),
                ),
                artifact_policy=ArtifactPolicy.DERIVED,
            ),
        ),
    )
