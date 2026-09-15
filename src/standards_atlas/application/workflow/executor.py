"""Workflow execution orchestration."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.application.ports import ExtractionState, WorkflowOperationRunner
from standards_atlas.application.workflow.models import (
    WorkflowExecutionResult,
    WorkflowPlan,
    WorkflowStage,
    WorkflowStep,
)
from standards_atlas.application.workflow.recovery import WorkflowRecovery


class WorkflowExecutor:
    def __init__(
        self, recovery: WorkflowRecovery, runner: WorkflowOperationRunner | None = None
    ) -> None:
        self._recovery = recovery
        self._runner = runner

    def execute(
        self,
        plan: WorkflowPlan,
        *,
        project_root: Path,
        runner: WorkflowOperationRunner | None = None,
        continue_after_review: bool = False,
    ) -> WorkflowExecutionResult:
        operation_runner = runner or self._runner
        if operation_runner is None:
            raise RuntimeError("Workflow execution requires an injected operation runner")
        executed: list[WorkflowStep] = []
        blocked_documents: set[str] = set()
        blocked_families: set[str] = set()

        self._recovery.begin_fresh_repetition(plan, project_root)

        for step in plan.steps:
            if not continue_after_review:
                if step.stage in {
                    WorkflowStage.CONTEXT_BASELINE,
                    WorkflowStage.ENRICHMENTS_BASELINE,
                    WorkflowStage.CORPUS_BUILD,
                    WorkflowStage.QUALIFICATION_MATRIX,
                    WorkflowStage.APPLICABILITY_DETAIL_ENRICHMENT,
                    WorkflowStage.APPLICABILITY_DECISION_POLICY,
                    WorkflowStage.QUALIFICATION_ARCHIVE,
                    WorkflowStage.KNOWLEDGE_ADOPT,
                    WorkflowStage.KNOWLEDGE_PUBLISH,
                    WorkflowStage.KNOWLEDGE_RESTORE,
                    WorkflowStage.CBOX_REPORT,
                } and (blocked_documents or blocked_families):
                    continue
                if step.family in blocked_families:
                    continue
                if step.document in blocked_documents:
                    continue
                if step.stage in {
                    WorkflowStage.MARKDOWN,
                    WorkflowStage.DOORSTOP,
                    WorkflowStage.DOORSTOP_PUBLISH,
                }:
                    family_documents = {
                        candidate.document
                        for candidate in plan.steps
                        if candidate.family == step.family
                        and candidate.stage == WorkflowStage.REVIEW
                    }
                    if family_documents & blocked_documents:
                        continue

            docling_state = self._recovery.docling_extraction_state(step, project_root)
            outputs_exist = (
                docling_state is ExtractionState.CURRENT
                if docling_state is not None
                else self._recovery.outputs_exist(step, project_root)
            )
            if plan.force and outputs_exist and step.stage not in plan.kept_stages:
                self._recovery.remove_outputs(step, project_root)
                outputs_exist = False

            if not outputs_exist:
                operation = self._recovery.execution_operation(step, docling_state)
                operation_runner.run(operation, project_root)
                self._recovery.record_completion(step, project_root)
                executed.append(step)

            if step.manual_gate and not continue_after_review:
                if step.stage == WorkflowStage.ATLASDATA:
                    blocked_families.add(step.family)
                elif self._recovery.alignment_requires_review(project_root, step.document):
                    blocked_documents.add(step.document)

        result = WorkflowExecutionResult(
            executed_steps=tuple(executed),
            blocked_documents=tuple(sorted(blocked_documents)),
            blocked_families=tuple(sorted(blocked_families)),
        )
        if result.completed:
            self._recovery.record_fresh_repetition_completion(plan, project_root)
        return result
