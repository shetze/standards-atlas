"""Filesystem repositories for versioned prompts and evaluation datasets."""

from __future__ import annotations

import hashlib
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
    """Load one complete prompt bundle and its bound shared resources.

    ``task_schema_version`` binds a prompt bundle to the task-owned schema.  Optional
    ``policy_binding`` and ``example_binding`` entries bind shared, versioned text resources that
    are composed into the effective system prompt.  Baseline bundles without these bindings retain
    their system prompt byte-for-byte, which keeps AP03 B0 reproducible while allowing P1/P2 to
    share one fachliche policy instead of maintaining parallel copies.
    """

    _REQUIRED_FILES = ("prompt.json", "schema.json", "system.txt", "user.txt")

    def __init__(
        self,
        root: Path,
        *,
        task_root: Path | None = None,
        policy_root: Path | None = None,
        example_root: Path | None = None,
    ) -> None:
        self._root = root
        semantic_root = root.parent
        self._task_root = task_root or semantic_root / "tasks"
        self._policy_root = policy_root or semantic_root / "policies"
        self._example_root = example_root or semantic_root / "examples"

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

        policy_id, policy_version, policy_text, policy_sha256 = self._load_text_binding(
            metadata.get("policy_binding"),
            root=self._policy_root,
            metadata_name="policy.json",
            text_name="policy.txt",
            kind="policy",
        )
        (
            example_set_id,
            example_set_version,
            example_text,
            example_set_sha256,
            example_partition,
        ) = self._load_example_binding(metadata.get("example_binding"))
        role_system_prompt = (root / "system.txt").read_text(encoding="utf-8").strip()
        system_prompt = _compose_system_prompt(
            role_system_prompt,
            policy_text=policy_text,
            example_text=example_text,
        )
        return PromptDefinition(
            task=task,
            version=version,
            description=str(metadata.get("description", "")),
            system_prompt=system_prompt,
            user_template=(root / "user.txt").read_text(encoding="utf-8").strip(),
            output_schema=schema,
            task_schema_version=task_schema_version,
            qualification_status=_optional_metadata_text(metadata.get("qualification_status")),
            baseline_id=_optional_metadata_text(metadata.get("baseline_id")),
            variant_id=_optional_metadata_text(metadata.get("variant_id")),
            policy_id=policy_id,
            policy_version=policy_version,
            policy_sha256=policy_sha256,
            example_set_id=example_set_id,
            example_set_version=example_set_version,
            example_set_partition=example_partition,
            example_set_sha256=example_set_sha256,
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

    def _load_text_binding(
        self,
        raw_binding: object,
        *,
        root: Path,
        metadata_name: str,
        text_name: str,
        kind: str,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        if raw_binding is None:
            return None, None, None, None
        if not isinstance(raw_binding, dict):
            raise ValueError(f"prompt {kind}_binding must be a JSON object")
        resource_id = str(raw_binding.get("id") or "").strip()
        version = str(raw_binding.get("version") or "").strip()
        if not resource_id or not version:
            raise ValueError(f"prompt {kind}_binding requires non-empty id and version")
        resource_root = root / resource_id / version
        metadata_path = resource_root / metadata_name
        text_path = resource_root / text_name
        if not metadata_path.is_file() or not text_path.is_file():
            raise ValueError(f"prompt binds missing {kind} resource {resource_id}@{version}")
        resource_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(resource_metadata, dict):
            raise ValueError(f"{kind} metadata for {resource_id}@{version} must be an object")
        if (
            resource_metadata.get("id") != resource_id
            or str(resource_metadata.get("version")) != version
        ):
            raise ValueError(f"{kind} identity mismatch for {resource_id}@{version}")
        text = text_path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"{kind} resource {resource_id}@{version} must not be empty")
        return resource_id, version, text, _sha256_text(text)

    def _load_example_binding(
        self, raw_binding: object
    ) -> tuple[str | None, str | None, str | None, str | None, str | None]:
        resource_id, version, text, digest = self._load_text_binding(
            raw_binding,
            root=self._example_root,
            metadata_name="examples.json",
            text_name="examples.txt",
            kind="example set",
        )
        if resource_id is None or version is None:
            return None, None, None, None, None
        metadata = json.loads(
            (self._example_root / resource_id / version / "examples.json").read_text(
                encoding="utf-8"
            )
        )
        partition = str(metadata.get("partition") or "").strip()
        if not partition:
            raise ValueError(f"example set {resource_id}@{version} requires a partition")
        if metadata.get("source_class") != "public_synthetic":
            raise ValueError(
                f"example set {resource_id}@{version} is not declared public_synthetic"
            )
        return resource_id, version, text, digest, partition


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


def _optional_metadata_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _compose_system_prompt(
    role_system_prompt: str,
    *,
    policy_text: str | None,
    example_text: str | None,
) -> str:
    parts: list[str] = []
    if policy_text is not None:
        parts.append("Shared engineering policy:\n" + policy_text)
    if example_text is not None:
        parts.append("Contrasting public-synthetic development examples:\n" + example_text)
    parts.append(
        "Role-specific instruction:\n" + role_system_prompt if parts else role_system_prompt
    )
    return "\n\n".join(parts)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
