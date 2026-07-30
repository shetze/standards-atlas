"""Filesystem repositories for versioned prompts and evaluation datasets."""

from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.application.evaluation.models import (
    EvaluationDataset,
    EvaluationExample,
    PromptDefinition,
)


class PromptRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def load(self, task: str, version: str) -> PromptDefinition:
        root = self._root / task / version
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
        payload = json.loads(
            (self._root / task / version / "dataset.json").read_text(encoding="utf-8")
        )
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
