"""Application port for structured local language-model inference."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

JsonObject = Mapping[str, Any]


class LlmGatewayError(RuntimeError):
    """Base exception for inference transport and response failures."""


class LlmUnavailableError(LlmGatewayError):
    """Raised when an inference endpoint is temporarily unavailable."""


class LlmTimeoutError(LlmUnavailableError):
    """Raised when one inference request exceeds the configured timeout."""


class LlmResponseError(LlmGatewayError):
    """Raised when an inference endpoint returns an invalid response."""

    def __init__(
        self,
        message: str,
        *,
        raw_content: str | None = None,
        raw_response: JsonObject | str | None = None,
        finish_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_content = raw_content
        self.raw_response = raw_response
        self.finish_reason = finish_reason


@dataclass(frozen=True)
class StructuredGenerationRequest:
    """Provider-independent request for schema-constrained text generation."""

    task: str
    system_prompt: str
    user_prompt: str
    output_schema: JsonObject
    prompt_version: str
    model: str | None = None
    temperature: float = 0.0
    seed: int | None = None
    max_tokens: int | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task.strip():
            raise ValueError("task must not be empty")
        if not self.prompt_version.strip():
            raise ValueError("prompt_version must not be empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ValueError("max_tokens must be positive")


@dataclass(frozen=True)
class TokenUsage:
    """Token counters reported by an inference provider."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class StructuredGenerationResult:
    """Structured output plus provenance required for reproducible enrichment."""

    value: JsonObject
    model: str
    provider: str
    prompt_version: str
    input_hash: str
    raw_response_hash: str
    duration_ms: int
    usage: TokenUsage | None = None
    cached: bool = False
    raw_response: JsonObject | str | None = None


@dataclass(frozen=True)
class LlmHealth:
    """Health information exposed without leaking provider-specific payloads."""

    available: bool
    models: tuple[str, ...] = ()
    detail: str | None = None


class LlmGateway(Protocol):
    """Port implemented by local or remote structured-generation adapters."""

    def health(self) -> LlmHealth:
        """Return endpoint availability and advertised model identifiers."""

    def generate_structured(
        self,
        request: StructuredGenerationRequest,
    ) -> StructuredGenerationResult:
        """Generate one JSON object constrained by ``request.output_schema``."""
