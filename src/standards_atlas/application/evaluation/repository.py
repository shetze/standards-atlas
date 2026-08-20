"""Filesystem repositories for versioned prompts and evaluation datasets."""

from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.application.evaluation.models import (
    EvaluationDataset,
    EvaluationExample,
    PromptDefinition,
)

_RESOURCE_TASK_ALIASES = {"semantic-profile-classification": "statement-function-classification"}


def _task_resource_root(root: Path, task: str, version: str) -> Path:
    direct = root / task / version
    if direct.is_dir():
        return direct
    alias = _RESOURCE_TASK_ALIASES.get(task)
    return root / alias / version if alias else direct


class PromptRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def load(self, task: str, version: str) -> PromptDefinition:
        root = _task_resource_root(self._root, task, version)
        metadata = json.loads((root / "prompt.json").read_text(encoding="utf-8"))
        schema = json.loads((root / "schema.json").read_text(encoding="utf-8"))
        return PromptDefinition(
            task=task,
            version=version,
            description=str(metadata.get("description", "")),
            system_prompt=(root / "system.txt").read_text(encoding="utf-8").strip(),
            user_template=(root / "user.txt").read_text(encoding="utf-8").strip(),
            output_schema=schema,
        )


class EvaluationDatasetRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def load(self, task: str, version: str) -> EvaluationDataset:
        dataset_path = _task_resource_root(self._root, task, version) / "dataset.json"
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
        examples = tuple(
            EvaluationExample(
                id=str(item["id"]),
                input=item["input"],
                expected=item["expected"],
                tags=tuple(item.get("tags", ())),
            )
            for item in payload["examples"]
        )
        return EvaluationDataset(task=task, version=version, examples=examples)


GoldenDatasetRepository = EvaluationDatasetRepository
