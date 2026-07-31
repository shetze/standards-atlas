from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from standards_atlas.adapters.llm import LlmConfig, OpenAICompatibleLlmGateway
from standards_atlas.application.ports.llm_gateway import (
    LlmResponseError,
    StructuredGenerationRequest,
)


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _request() -> StructuredGenerationRequest:
    return StructuredGenerationRequest(
        task="clause-summary",
        system_prompt="Return a concise summary.",
        user_prompt="The supplier shall verify the safety plan.",
        output_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
        prompt_version="clause-summary-v1",
        seed=7,
        max_tokens=100,
    )


def test_health_returns_advertised_models(tmp_path: Path) -> None:
    gateway = OpenAICompatibleLlmGateway(LlmConfig(cache_directory=tmp_path / "cache"))

    with patch(
        "standards_atlas.adapters.llm.openai_compatible.urlopen",
        return_value=_Response({"data": [{"id": "granite"}, {"id": "qwen"}]}),
    ):
        health = gateway.health()

    assert health.available
    assert health.models == ("granite", "qwen")


def test_health_treats_connection_reset_as_temporarily_unavailable(tmp_path: Path) -> None:
    gateway = OpenAICompatibleLlmGateway(LlmConfig(cache_directory=tmp_path / "cache"))

    with patch(
        "standards_atlas.adapters.llm.openai_compatible.urlopen",
        side_effect=ConnectionResetError(104, "Connection reset by peer"),
    ):
        health = gateway.health()

    assert not health.available
    assert health.detail is not None
    assert "Connection reset by peer" in health.detail


def test_generates_structured_result_with_provenance_and_usage(tmp_path: Path) -> None:
    gateway = OpenAICompatibleLlmGateway(
        LlmConfig(model="granite", cache_directory=tmp_path / "cache")
    )
    response = {
        "model": "granite-local",
        "choices": [{"message": {"content": '{"summary":"Verify the safety plan."}'}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
    }

    with patch(
        "standards_atlas.adapters.llm.openai_compatible.urlopen",
        return_value=_Response(response),
    ) as urlopen:
        result = gateway.generate_structured(_request())

    outbound = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert outbound["response_format"]["type"] == "json_schema"
    assert outbound["seed"] == 7
    assert result.value == {"summary": "Verify the safety plan."}
    assert result.model == "granite-local"
    assert result.prompt_version == "clause-summary-v1"
    assert result.usage is not None
    assert result.usage.total_tokens == 20
    assert len(result.input_hash) == 64
    assert len(result.raw_response_hash) == 64
    assert not result.cached


def test_reuses_cached_result_without_second_request(tmp_path: Path) -> None:
    gateway = OpenAICompatibleLlmGateway(
        LlmConfig(model="granite", cache_directory=tmp_path / "cache")
    )
    response = {
        "model": "granite",
        "choices": [{"message": {"content": '{"summary":"Cached summary."}'}}],
    }

    with patch(
        "standards_atlas.adapters.llm.openai_compatible.urlopen",
        return_value=_Response(response),
    ) as urlopen:
        first = gateway.generate_structured(_request())
        second = gateway.generate_structured(_request())

    assert urlopen.call_count == 1
    assert not first.cached
    assert second.cached
    assert second.value == first.value


def test_accepts_json_wrapped_in_markdown_fence(tmp_path: Path) -> None:
    gateway = OpenAICompatibleLlmGateway(
        LlmConfig(model="granite", cache_directory=tmp_path / "cache")
    )
    response = {
        "model": "granite",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": '```json\n{"summary":"Valid."}\n```'},
            }
        ],
    }
    with patch(
        "standards_atlas.adapters.llm.openai_compatible.urlopen",
        return_value=_Response(response),
    ):
        result = gateway.generate_structured(_request())
    assert result.value == {"summary": "Valid."}


def test_invalid_json_exposes_raw_response_and_finish_reason(tmp_path: Path) -> None:
    gateway = OpenAICompatibleLlmGateway(
        LlmConfig(model="granite", cache_directory=tmp_path / "cache")
    )
    response = {
        "model": "granite",
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": '{"summary":"truncated'},
            }
        ],
    }
    with patch(
        "standards_atlas.adapters.llm.openai_compatible.urlopen",
        return_value=_Response(response),
    ):
        try:
            gateway.generate_structured(_request())
        except LlmResponseError as error:
            assert error.raw_content == '{"summary":"truncated'
            assert error.raw_response == response
            assert error.finish_reason == "length"
        else:
            raise AssertionError("expected LlmResponseError")
