"""Filesystem repositories for versioned prompts and semantic gold datasets."""

from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.application.semantic_evaluation.models import (
    GoldenDataset,
    GoldenExample,
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


class GoldenDatasetRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def load(self, task: str, version: str) -> GoldenDataset:
        payload = json.loads(
            (self._root / task / version / "dataset.json").read_text(encoding="utf-8")
        )
        examples = tuple(
            GoldenExample(
                id=str(item["id"]),
                input=item["input"],
                expected=item["expected"],
                tags=tuple(item.get("tags", ())),
            )
            for item in payload["examples"]
        )
        return GoldenDataset(task=task, version=version, examples=examples)
