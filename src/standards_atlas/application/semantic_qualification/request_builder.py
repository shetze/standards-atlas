"""Build durable structured-generation requests for semantic proposals."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.ports.llm_gateway import StructuredGenerationRequest
from standards_atlas.application.semantic_qualification.annotations import ClauseReference


def build_proposal_request(
    config: Any,
    prompt: PromptDefinition,
    item_input: Mapping[str, Any],
    task: Any,
) -> StructuredGenerationRequest:
    """Build one structured-generation request from a corpus item."""
    content = dict(item_input.get("content", {}))
    context = dict(item_input.get("context", {}))
    values = {
        "content": content.get("text", ""),
        "content_hash": content.get("hash", ""),
        "context_json": json.dumps(context, ensure_ascii=False, sort_keys=True),
        **context,
    }
    try:
        user_prompt = prompt.user_template.format(**values)
    except KeyError as exc:
        raise ValueError(f"prompt references unavailable field: {exc.args[0]}") from exc
    return StructuredGenerationRequest(
        task=config.task,
        system_prompt=prompt.system_prompt,
        user_prompt=user_prompt,
        output_schema=prompt.output_schema,
        prompt_version=config.prompt_version,
        model=config.model,
        temperature=config.temperature,
        seed=config.seed,
        max_tokens=config.max_tokens,
        reasoning_enabled=config.reasoning_enabled,
        metadata={
            "corpus_id": config.corpus_id,
            "dataset_version": config.dataset_version,
            "task_version": task.version,
            "content_hash": content.get("hash"),
            "clause_context": context,
        },
    )


def build_clause_reference(item_input: Mapping[str, Any]) -> ClauseReference:
    """Build the durable clause identity stored with a proposal."""
    content = dict(item_input["content"])
    context = dict(item_input["context"])
    return ClauseReference(
        knowledge_domain=context["knowledge_domain"],
        document_key=context["document_key"],
        clause_id=context["clause_id"],
        content_hash=content["hash"],
    )


def serialize_generation_request(request: StructuredGenerationRequest) -> dict[str, Any]:
    """Return the stable JSON payload persisted for a generation request."""
    return {
        "task": request.task,
        "system_prompt": request.system_prompt,
        "user_prompt": request.user_prompt,
        "output_schema": dict(request.output_schema),
        "prompt_version": request.prompt_version,
        "model": request.model,
        "temperature": request.temperature,
        "seed": request.seed,
        "max_tokens": request.max_tokens,
        "reasoning_enabled": request.reasoning_enabled,
        "metadata": dict(request.metadata),
    }
