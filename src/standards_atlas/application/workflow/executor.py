"""Workflow execution orchestration."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol

from standards_atlas.application.ports import ExtractionState
from standards_atlas.application.workflow.models import (
    WorkflowExecutionResult,
    WorkflowPlan,
    WorkflowStage,
    WorkflowStep,
)
from standards_atlas.application.workflow.recovery import WorkflowRecovery


class CommandRunner(Protocol):
    def run(self, command: tuple[str, ...], cwd: Path) -> None: ...


class SubprocessCommandRunner:
    def run(self, command: tuple[str, ...], cwd: Path) -> None:
        subprocess.run(command, cwd=cwd, check=True)  # noqa: S603


class WorkflowExecutor:
    def __init__(self, recovery: WorkflowRecovery) -> None:
        self._recovery = recovery

    def execute(
        self,
        plan: WorkflowPlan,
        *,
        project_root: Path,
        runner: CommandRunner | None = None,
        continue_after_review: bool = False,
    ) -> WorkflowExecutionResult:
        command_runner = runner or SubprocessCommandRunner()
        executed: list[WorkflowStep] = []
        blocked_documents: set[str] = set()
        blocked_families: set[str] = set()

        for step in plan.steps:
            if not continue_after_review:
                if step.stage in {
                    WorkflowStage.CORPUS_BUILD,
                    WorkflowStage.QUALIFICATION_MATRIX,
                } and (blocked_documents or blocked_families):
                    continue
                if step.family in blocked_families:
                    continue
                if step.document in blocked_documents:
                    continue
                if step.stage in {
                    WorkflowStage.COMPOSE,
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
                command = self._recovery.execution_command(step, docling_state)
                command_runner.run(command, project_root)
                self._recovery.record_completion(step, project_root)
                executed.append(step)

            if step.manual_gate and not continue_after_review:
                if step.stage == WorkflowStage.ATLASDATA:
                    blocked_families.add(step.family)
                elif self._recovery.alignment_requires_review(project_root, step.document):
                    blocked_documents.add(step.document)

        return WorkflowExecutionResult(
            executed_steps=tuple(executed),
            blocked_documents=tuple(sorted(blocked_documents)),
            blocked_families=tuple(sorted(blocked_families)),
        )
