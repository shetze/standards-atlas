"""Packaged-resource prompt catalog for prompt-workbench clients."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.prompt_workbench.compiler import PromptCompiler
from standards_atlas.application.prompt_workbench.models import PromptCatalogEntry


class ResourcePromptCatalog:
    """Discover complete versioned prompt bundles below one resource root."""

    _REQUIRED_FILES = frozenset({"prompt.json", "schema.json", "system.txt", "user.txt"})

    def __init__(self, root: Path) -> None:
        self._root = root
        self._repository = PromptRepository(root)
        self._compiler = PromptCompiler()

    def list_prompts(self) -> tuple[PromptCatalogEntry, ...]:
        prompts: list[PromptCatalogEntry] = []
        if not self._root.is_dir():
            return ()
        for task_path in sorted(item for item in self._root.iterdir() if item.is_dir()):
            for version_path in sorted(item for item in task_path.iterdir() if item.is_dir()):
                if not self._REQUIRED_FILES.issubset(
                    {item.name for item in version_path.iterdir() if item.is_file()}
                ):
                    continue
                definition = self._repository.load(task_path.name, version_path.name)
                prompts.append(
                    PromptCatalogEntry(
                        task=definition.task,
                        version=definition.version,
                        description=definition.description,
                        placeholders=self._compiler.placeholders(definition.user_template),
                    )
                )
        return tuple(prompts)

    def load_prompt(self, task: str, version: str) -> PromptDefinition:
        return self._repository.load(task, version)
