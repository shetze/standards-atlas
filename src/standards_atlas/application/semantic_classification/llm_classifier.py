"""Production LLM classifier for composed semantic profiles."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

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
    """Classify semantic profile dimensions through one schema-constrained LLM request."""

    classifier_id = "qualified-llm"

    def __init__(self, gateway: LlmGateway, *, model: str | None = None) -> None:
        self._gateway = gateway
        self._model = model

    def classify(
        self,
        context: SemanticClassificationContext,
        definitions: dict[str, OntologyDefinition],
    ) -> tuple[SemanticDimensionResult, ...]:
        properties: dict[str, Any] = {}
        for dimension, definition in definitions.items():
            properties[dimension] = {
                "type": "array",
                "items": {"type": "string", "enum": list(definition.values)},
                "uniqueItems": True,
            }
        schema = {
            "type": "object",
            "properties": properties,
            "required": list(definitions),
            "additionalProperties": False,
        }
        payload = {
            "content": context.content,
            "structural_context": context.structural_context,
            "metadata": context.metadata,
            "ontology": {
                key: {
                    "description": value.description,
                    "values": list(value.values),
                    "semantics": value.semantics,
                }
                for key, value in definitions.items()
            },
        }
        request = StructuredGenerationRequest(
            task="production-ontology-classification",
            system_prompt=(
                "Classify the clause using only the supplied clause content, structural "
                "context, and ontology definitions. Structural context is evidence, not "
                "semantic truth. Return only values declared by each ontology dimension. "
                "Use an empty array when the evidence is insufficient."
            ),
            user_prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            output_schema=schema,
            prompt_version="1.1.0",
            model=self._model,
            temperature=0.0,
            seed=0,
            max_tokens=512,
            reasoning_enabled=False,
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
                max_tokens=1024,
            )
            result = self._gateway.generate_structured(retry)
        return tuple(
            SemanticDimensionResult(
                dimension=dimension,
                values=tuple(str(item) for item in result.value.get(dimension, ())),
            )
            for dimension in definitions
        )
