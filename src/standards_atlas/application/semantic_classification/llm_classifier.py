"""Production LLM classifier for composed semantic profiles."""

from __future__ import annotations

import json
from dataclasses import replace

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.ontology.definition import OntologyDefinition
from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    LlmResponseError,
    StructuredGenerationRequest,
)
from standards_atlas.application.semantic_classification.engine import (
    SemanticClassificationContext,
    SemanticDimensionResult,
)


class LlmSemanticClassifier:
    """Run the qualified semantic-classification task with one production model.

    Qualification and production intentionally have different execution policies,
    but they share the same versioned task/prompt contract. Qualification may run a
    multi-model cascade; production uses one configured model and persists its
    result.
    """

    classifier_id = "qualified-llm"

    def __init__(
        self,
        gateway: LlmGateway,
        *,
        prompt: PromptDefinition,
        task_version: str,
        model: str | None = None,
    ) -> None:
        self._gateway = gateway
        self._prompt = prompt
        self._task_version = task_version
        self._model = model

    def classify(
        self,
        context: SemanticClassificationContext,
        definitions: dict[str, OntologyDefinition],
    ) -> tuple[SemanticDimensionResult, ...]:
        context_payload = dict(context.metadata)
        context_payload["structural_context"] = context.structural_context
        values = {
            "content": context.content,
            "content_hash": "",
            "context_json": json.dumps(context_payload, ensure_ascii=False, sort_keys=True),
            **context_payload,
        }
        try:
            user_prompt = self._prompt.user_template.format(**values)
        except KeyError as exc:
            raise ValueError(
                f"qualified semantic prompt references unavailable field: {exc.args[0]}"
            ) from exc

        request = StructuredGenerationRequest(
            task=self._prompt.task,
            system_prompt=self._prompt.system_prompt,
            user_prompt=user_prompt,
            output_schema=self._prompt.output_schema,
            prompt_version=self._prompt.version,
            model=self._model,
            temperature=0.0,
            seed=0,
            max_tokens=1024,
            reasoning_enabled=False,
            metadata={"task_version": self._task_version},
        )
        try:
            result = self._gateway.generate_structured(request)
        except LlmResponseError as error:
            if error.finish_reason != "length":
                raise
            retry = replace(
                request,
                system_prompt=(
                    request.system_prompt
                    + " The previous response was truncated. Return only the compact JSON "
                    "object required by the schema, with no explanations or extra fields."
                ),
                max_tokens=2048,
            )
            result = self._gateway.generate_structured(retry)

        return tuple(
            SemanticDimensionResult(
                dimension=dimension,
                values=tuple(str(item) for item in result.value.get(dimension, ())),
                presence=(
                    bool(result.value.get("applicability_present", False))
                    if dimension == "applicability_functions"
                    else None
                ),
            )
            for dimension in definitions
        )
