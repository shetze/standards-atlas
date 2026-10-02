"""Shared compilation of versioned source-bound structured-generation requests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.ports.llm_gateway import StructuredGenerationRequest

SOURCE_BOUND_REQUEST_TEMPLATE = "{request_json}"


def semantic_prompt_repository() -> PromptRepository:
    """Return the installed semantic prompt repository with task-schema validation enabled."""

    semantic_root = Path(__file__).resolve().parents[2] / "resources" / "semantic"
    return PromptRepository(
        semantic_root / "prompts",
        task_root=semantic_root / "tasks",
    )


def build_source_bound_generation_request(
    *,
    repository: PromptRepository,
    task: str,
    prompt_version: str,
    task_schema_version: str,
    payload: Mapping[str, object],
    model: str | None,
    temperature: float,
    metadata: Mapping[str, Any],
) -> StructuredGenerationRequest:
    """Compile the exact JSON payload through one task/schema-bound packaged prompt.

    AP02 already established the source package and payload contracts.  AP03 Series A deliberately
    does not change those contents: B0 uses a one-variable template whose rendering is exactly the
    former ``json.dumps(..., ensure_ascii=False)`` request body.  Additional prompt/task identity is
    recorded only in request metadata.
    """

    prompt = repository.load(task, prompt_version)
    _validate_source_bound_prompt(
        prompt,
        task=task,
        prompt_version=prompt_version,
        task_schema_version=task_schema_version,
    )
    request_json = json.dumps(dict(payload), ensure_ascii=False)
    user_prompt = prompt.user_template.format(request_json=request_json)
    enriched_metadata = dict(metadata)
    enriched_metadata.update(
        {
            "prompt_task_schema_version": task_schema_version,
            "prompt_system_sha256": _sha256_text(prompt.system_prompt),
            "prompt_user_template_sha256": _sha256_text(prompt.user_template),
            "prompt_schema_sha256": _canonical_sha256(prompt.output_schema),
        }
    )
    return StructuredGenerationRequest(
        task=task,
        prompt_version=prompt_version,
        model=model,
        temperature=temperature,
        output_schema=prompt.output_schema,
        system_prompt=prompt.system_prompt,
        user_prompt=user_prompt,
        metadata=enriched_metadata,
    )


def _validate_source_bound_prompt(
    prompt: PromptDefinition,
    *,
    task: str,
    prompt_version: str,
    task_schema_version: str,
) -> None:
    if prompt.task != task or prompt.version != prompt_version:
        raise ValueError("loaded prompt identity does not match requested source-bound prompt")
    if prompt.task_schema_version != task_schema_version:
        raise ValueError(
            f"prompt {task}@{prompt_version} must bind task schema {task_schema_version!r}; "
            f"got {prompt.task_schema_version!r}"
        )
    if prompt.user_template != SOURCE_BOUND_REQUEST_TEMPLATE:
        raise ValueError(
            f"source-bound prompt {task}@{prompt_version} must use exactly "
            f"{SOURCE_BOUND_REQUEST_TEMPLATE!r} as its request template"
        )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
