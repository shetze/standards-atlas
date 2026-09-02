"""Catalog ports consumed by the prompt-workbench application service."""

from __future__ import annotations

from typing import Protocol

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.prompt_workbench.models import (
    ModelCatalogEntry,
    PromptCatalogEntry,
)


class PromptCatalog(Protocol):
    """Discover and load versioned packaged prompt contracts."""

    def list_prompts(self) -> tuple[PromptCatalogEntry, ...]: ...

    def load_prompt(self, task: str, version: str) -> PromptDefinition: ...


class ModelCatalog(Protocol):
    """Discover manifest-declared RamaLama models."""

    def list_models(self) -> tuple[ModelCatalogEntry, ...]: ...

    def get_model(self, model_id: str) -> ModelCatalogEntry: ...
