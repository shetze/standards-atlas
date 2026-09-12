"""Build durable structured-generation requests for semantic proposals."""

from __future__ import annotations

import json
from collections.abc import Mapping
from string import Formatter
from typing import Any

from standards_atlas.application.context.canonical_cbox import context_fingerprint
from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.ports.llm_gateway import StructuredGenerationRequest
from standards_atlas.application.semantic_qualification.annotations import ClauseReference
from standards_atlas.application.semantic_qualification.context_framing import (
    frame_qualification_context,
    resolve_cbox_frame_policy,
)
from standards_atlas.application.semantic_qualification.context_projection import (
    render_cbox_context,
)


def build_proposal_request(
    config: Any,
    prompt: PromptDefinition,
    item_input: Mapping[str, Any],
    task: Any,
    *,
    extra_template_values: Mapping[str, Any] | None = None,
) -> StructuredGenerationRequest:
    """Build one structured-generation request from a corpus item."""
    content = dict(item_input.get("content", {}))
    context = dict(item_input.get("context", {}))
    frame_name = getattr(config, "cbox_frame", "full-context-v1")
    frame_policy = resolve_cbox_frame_policy(frame_name)
    framed_context = frame_qualification_context(
        context,
        frame_policy,
        task=config.task,
        text=content.get("text", ""),
        content_hash=content.get("hash"),
    )
    values = {
        **dict(framed_context.values),
        "clause_id": context.get("clause_id", ""),
        "document_key": framed_context.values.get("document_key", ""),
        "reference": framed_context.values.get("reference", ""),
        "heading": framed_context.values.get("heading", ""),
        "content": content.get("text", ""),
        "text": content.get("text", ""),
        "content_hash": content.get("hash", ""),
        "context_json": json.dumps(framed_context.values, ensure_ascii=False, sort_keys=True),
        "context_text": render_cbox_context(framed_context),
        "metadata": json.dumps(
            {
                name: framed_context.values[name]
                for name in ("document_key", "reference", "heading", "clause_type")
                if name in framed_context.values
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        "structural_context": json.dumps(
            framed_context.values.get("structural_context", {}), sort_keys=True
        ),
    }
    if extra_template_values:
        collisions = set(values).intersection(extra_template_values)
        if collisions:
            raise ValueError(
                "extra prompt fields cannot replace source fields: " + ", ".join(sorted(collisions))
            )
        values.update(extra_template_values)
    # Hash selected facts rather than their prose rendering. A renderer-only
    # change does not make accepted predictions stale; a changed prompt does.
    fields = {field for _, field, _, _ in Formatter().parse(prompt.user_template) if field}
    fingerprint_values = {
        field: (
            dict(framed_context.values)
            if field in {"context_text", "context_json"}
            else values.get(field)
        )
        for field in fields
    }
    contract = (
        task.model_dump(mode="json")
        if hasattr(task, "model_dump")
        else {
            "version": task.version,
        }
    )
    fingerprint = context_fingerprint(
        {
            "contract": "qualification-input-v1",
            "task": contract,
            "source": {"hash": content.get("hash"), "text": content.get("text", "")},
            "frame": {"id": framed_context.policy_id, "version": framed_context.policy_version},
            "isolation": "qualification-targets-v1",
            "prompt": {
                "system": prompt.system_prompt,
                "template": prompt.user_template,
                "schema": dict(prompt.output_schema),
                "version": config.prompt_version,
            },
            "values": fingerprint_values,
            "generation": {
                key: getattr(config, key, None)
                for key in (
                    "task",
                    "provider",
                    "model",
                    "temperature",
                    "seed",
                    "max_tokens",
                    "reasoning_enabled",
                    "adaptive_interview",
                    "adaptive_question_max_tokens",
                    "truncation_retry_max_tokens",
                    "retry_on_truncation",
                )
            },
        }
    )
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
            "qualification_input_fingerprint": fingerprint,
            "qualification_isolation": "qualification-targets-v1",
            "cbox_frame": {
                "id": framed_context.policy_id,
                "version": framed_context.policy_version,
            },
            "framed_cbox": dict(framed_context.values),
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
