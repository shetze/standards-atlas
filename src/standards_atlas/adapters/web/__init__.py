"""Local web adapters for interactive Standards Atlas services."""

from standards_atlas.adapters.web.prompt_workbench import (
    PromptWorkbenchHttpConfig,
    PromptWorkbenchWebDependencies,
    create_prompt_workbench_app,
    run_prompt_workbench_server,
)
from standards_atlas.adapters.web.review_workbench import (
    ReviewWorkbenchHttpConfig,
    create_review_workbench_app,
    run_review_workbench_server,
)

__all__ = [
    "ReviewWorkbenchHttpConfig",
    "create_review_workbench_app",
    "run_review_workbench_server",
    "PromptWorkbenchHttpConfig",
    "PromptWorkbenchWebDependencies",
    "create_prompt_workbench_app",
    "run_prompt_workbench_server",
]
