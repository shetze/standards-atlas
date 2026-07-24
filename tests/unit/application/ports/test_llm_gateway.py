from __future__ import annotations

import pytest

from standards_atlas.application.ports.llm_gateway import StructuredGenerationRequest

_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}


def test_structured_request_rejects_empty_task() -> None:
    with pytest.raises(ValueError, match="task"):
        StructuredGenerationRequest(
            task=" ",
            system_prompt="Summarize clauses.",
            user_prompt="Clause text",
            output_schema=_SCHEMA,
            prompt_version="1",
        )


def test_structured_request_rejects_invalid_temperature() -> None:
    with pytest.raises(ValueError, match="temperature"):
        StructuredGenerationRequest(
            task="clause-summary",
            system_prompt="Summarize clauses.",
            user_prompt="Clause text",
            output_schema=_SCHEMA,
            prompt_version="1",
            temperature=2.1,
        )
