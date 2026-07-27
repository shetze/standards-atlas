"""OpenAI-compatible adapter for local llama.cpp inference servers."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from standards_atlas.adapters.llm.config import LlmConfig
from standards_atlas.application.ports.llm_gateway import (
    LlmHealth,
    StructuredGenerationRequest,
    StructuredGenerationResult,
    TokenUsage,
)


class LlmGatewayError(RuntimeError):
    """Base exception for inference transport and response failures."""


class LlmUnavailableError(LlmGatewayError):
    """Raised when the configured inference endpoint cannot be reached."""


class LlmResponseError(LlmGatewayError):
    """Raised when the inference endpoint returns an invalid response."""


class OpenAICompatibleLlmGateway:
    """Schema-constrained gateway compatible with RamaLama's llama.cpp server."""

    provider = "openai-compatible"

    def __init__(self, config: LlmConfig) -> None:
        self._config = config

    def health(self) -> LlmHealth:
        try:
            payload = self._request_json("GET", "models")
            model_entries = payload.get("data", ())
            models = tuple(
                str(entry["id"])
                for entry in model_entries
                if isinstance(entry, Mapping) and entry.get("id")
            )
            return LlmHealth(available=True, models=models)
        except LlmGatewayError as error:
            return LlmHealth(available=False, detail=str(error))

    def generate_structured(
        self,
        request: StructuredGenerationRequest,
    ) -> StructuredGenerationResult:
        model = request.model or self._config.model
        input_hash = _input_hash(request, model)
        cached = self._load_cache(input_hash)
        if cached is not None:
            return replace(cached, cached=True)

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": _schema_name(request.task),
                    "strict": True,
                    "schema": dict(request.output_schema),
                },
            },
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        started = time.monotonic()
        response = self._request_json("POST", "chat/completions", payload)
        duration_ms = round((time.monotonic() - started) * 1000)
        raw_content = _extract_content(response)
        try:
            value = json.loads(raw_content)
        except json.JSONDecodeError as error:
            raise LlmResponseError("LLM response content is not valid JSON") from error
        if not isinstance(value, Mapping):
            raise LlmResponseError("LLM structured response must be a JSON object")

        result = StructuredGenerationResult(
            value=dict(value),
            model=str(response.get("model") or model),
            provider=self.provider,
            prompt_version=request.prompt_version,
            input_hash=input_hash,
            raw_response_hash=_sha256(raw_content.encode("utf-8")),
            duration_ms=duration_ms,
            usage=_parse_usage(response.get("usage")),
        )
        self._store_cache(result)
        return result

    def _request_json(
        self,
        method: str,
        endpoint: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        url = urljoin(self._config.base_url.rstrip("/") + "/", endpoint)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self._config.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise LlmResponseError(f"LLM endpoint returned HTTP {error.code}: {detail}") from error
        except (URLError, TimeoutError, ConnectionError, OSError) as error:
            raise LlmUnavailableError(f"LLM endpoint is unavailable: {error}") from error
        except json.JSONDecodeError as error:
            raise LlmResponseError("LLM endpoint returned invalid JSON") from error
        if not isinstance(decoded, Mapping):
            raise LlmResponseError("LLM endpoint response must be a JSON object")
        return decoded

    def _cache_path(self, input_hash: str) -> Path | None:
        directory = self._config.cache_directory
        return directory / f"{input_hash}.json" if directory is not None else None

    def _load_cache(self, input_hash: str) -> StructuredGenerationResult | None:
        path = self._cache_path(input_hash)
        if path is None or not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            usage_payload = payload.get("usage")
            usage = TokenUsage(**usage_payload) if usage_payload else None
            return StructuredGenerationResult(
                value=payload["value"],
                model=payload["model"],
                provider=payload["provider"],
                prompt_version=payload["prompt_version"],
                input_hash=payload["input_hash"],
                raw_response_hash=payload["raw_response_hash"],
                duration_ms=payload["duration_ms"],
                usage=usage,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise LlmResponseError(f"Invalid LLM cache entry: {path}") from error

    def _store_cache(self, result: StructuredGenerationResult) -> None:
        path = self._cache_path(result.input_hash)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        usage = None
        if result.usage is not None:
            usage = {
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
            }
        payload = {
            "value": dict(result.value),
            "model": result.model,
            "provider": result.provider,
            "prompt_version": result.prompt_version,
            "input_hash": result.input_hash,
            "raw_response_hash": result.raw_response_hash,
            "duration_ms": result.duration_ms,
            "usage": usage,
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)


def _extract_content(response: Mapping[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise LlmResponseError("LLM response does not contain message content") from error
    if not isinstance(content, str):
        raise LlmResponseError("LLM message content must be text")
    return content


def _parse_usage(value: object) -> TokenUsage | None:
    if not isinstance(value, Mapping):
        return None
    return TokenUsage(
        prompt_tokens=_optional_int(value.get("prompt_tokens")),
        completion_tokens=_optional_int(value.get("completion_tokens")),
        total_tokens=_optional_int(value.get("total_tokens")),
    )


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _input_hash(request: StructuredGenerationRequest, model: str) -> str:
    canonical = json.dumps(
        {
            "task": request.task,
            "system_prompt": request.system_prompt,
            "user_prompt": request.user_prompt,
            "output_schema": request.output_schema,
            "prompt_version": request.prompt_version,
            "model": model,
            "temperature": request.temperature,
            "seed": request.seed,
            "max_tokens": request.max_tokens,
            "metadata": request.metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return _sha256(canonical.encode("utf-8"))


def _schema_name(task: str) -> str:
    normalized = "".join(character if character.isalnum() else "_" for character in task)
    return normalized.strip("_")[:64] or "structured_generation"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
