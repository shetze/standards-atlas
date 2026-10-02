"""Filesystem repositories for versioned prompts and evaluation datasets."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from standards_atlas.application.evaluation.models import (
    EvaluationDataset,
    EvaluationExample,
    PromptDefinition,
)


def _task_resource_root(root: Path, task: str, version: str) -> Path:
    direct = root / task / version
    if direct.is_dir():
        return direct
    return direct


class PromptRepository:
    """Load one complete prompt bundle and, when declared, its task-owned schema.

    ``task_schema_version`` in ``prompt.json`` binds a prompt bundle to the existing semantic-task
    resource tree.  The prompt-local ``schema.json`` is retained because prompt tooling expects a
    self-contained bundle, but it is accepted only when it is semantically equal to the
    task-owned schema.  This prevents an adapter, workbench and task resource from silently
    developing independent output contracts.
    """

    _REQUIRED_FILES = ("prompt.json", "schema.json", "system.txt", "user.txt")

    def __init__(self, root: Path, *, task_root: Path | None = None) -> None:
        self._root = root
        self._task_root = task_root or root.parent / "tasks"

    def load(self, task: str, version: str) -> PromptDefinition:
        root = _task_resource_root(self._root, task, version)
        missing = tuple(name for name in self._REQUIRED_FILES if not (root / name).is_file())
        if missing:
            raise ValueError(
                f"incomplete prompt bundle {task}@{version}: missing {', '.join(missing)}"
            )
        metadata = json.loads((root / "prompt.json").read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError(f"prompt metadata for {task}@{version} must be a JSON object")
        declared_task = metadata.get("task")
        if declared_task is not None and declared_task != task:
            raise ValueError(
                f"prompt bundle task mismatch: requested {task!r}, metadata declares "
                f"{declared_task!r}"
            )
        declared_version = metadata.get("version")
        if declared_version is not None and declared_version != version:
            raise ValueError(
                f"prompt bundle version mismatch: requested {version!r}, metadata declares "
                f"{declared_version!r}"
            )
        schema = json.loads((root / "schema.json").read_text(encoding="utf-8"))
        task_schema_version = metadata.get("task_schema_version")
        if task_schema_version is not None:
            task_schema_version = str(task_schema_version)
            self._validate_task_schema_binding(
                task=task,
                task_schema_version=task_schema_version,
                prompt_schema=schema,
            )
        return PromptDefinition(
            task=task,
            version=version,
            description=str(metadata.get("description", "")),
            system_prompt=(root / "system.txt").read_text(encoding="utf-8").strip(),
            user_template=(root / "user.txt").read_text(encoding="utf-8").strip(),
            output_schema=schema,
            task_schema_version=task_schema_version,
        )

    def _validate_task_schema_binding(
        self,
        *,
        task: str,
        task_schema_version: str,
        prompt_schema: object,
    ) -> None:
        task_root = self._task_root / task / task_schema_version
        task_metadata_path = task_root / "task.yaml"
        task_schema_path = task_root / "schema.json"
        missing = tuple(
            path.name for path in (task_metadata_path, task_schema_path) if not path.is_file()
        )
        if missing:
            raise ValueError(
                f"prompt bundle {task} binds missing task resource {task}@{task_schema_version}: "
                + ", ".join(missing)
            )
        metadata = yaml.safe_load(task_metadata_path.read_text(encoding="utf-8")) or {}
        if not isinstance(metadata, dict):
            raise ValueError(
                f"semantic task {task}@{task_schema_version} metadata must be a mapping"
            )
        if metadata.get("task") != task or str(metadata.get("version")) != task_schema_version:
            raise ValueError(f"semantic task identity mismatch for {task}@{task_schema_version}")
        task_schema = json.loads(task_schema_path.read_text(encoding="utf-8"))
        if task_schema != prompt_schema:
            raise ValueError(
                f"prompt schema differs from task-owned schema for {task}@{task_schema_version}"
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
