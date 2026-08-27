"""Compatibility façade composing workflow planning and execution."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.application.catalog import StandardCatalog
from standards_atlas.application.workflow.executor import (
    CommandRunner,
    WorkflowExecutor,
)
from standards_atlas.application.workflow.models import (
    WorkflowExecutionResult,
    WorkflowPlan,
    WorkflowStage,
)
from standards_atlas.application.workflow.planner import WorkflowPlanner


class EndToEndWorkflowService:
    """Compose planner, executor, and recovery while preserving the public API."""

    _doorstop_parent = staticmethod(WorkflowPlanner._doorstop_parent)
    _content_selection_args = staticmethod(WorkflowPlanner._content_selection_args)
    _apply_force_policy = staticmethod(WorkflowPlanner._apply_force_policy)

    def __init__(
        self, planner: WorkflowPlanner | None = None, executor: WorkflowExecutor | None = None
    ) -> None:
        self.planner = planner or WorkflowPlanner()
        self.executor = executor

    def plan(
        self,
        catalog: StandardCatalog,
        *,
        family_keys: tuple[str, ...],
        catalog_root: Path,
        force: bool = False,
        keep_stages: tuple[WorkflowStage, ...] = (),
        hierarchy_key: str | None = None,
        include_semantic_classification: bool = False,
    ) -> WorkflowPlan:
        return self.planner.plan(
            catalog,
            family_keys=family_keys,
            catalog_root=catalog_root,
            force=force,
            keep_stages=keep_stages,
            hierarchy_key=hierarchy_key,
            include_semantic_classification=include_semantic_classification,
        )

    def execute(
        self,
        plan: WorkflowPlan,
        *,
        project_root: Path,
        runner: CommandRunner | None = None,
        continue_after_review: bool = False,
    ) -> WorkflowExecutionResult:
        if self.executor is None:
            raise RuntimeError("Workflow execution requires an injected WorkflowExecutor")
        return self.executor.execute(
            plan,
            project_root=project_root,
            runner=runner,
            continue_after_review=continue_after_review,
        )
