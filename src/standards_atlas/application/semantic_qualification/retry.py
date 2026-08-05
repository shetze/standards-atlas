"""Retry policy for structured semantic proposal generation."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace

from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
    StructuredGenerationRequest,
)

RetryReporter = Callable[[int, Exception], None]


def generate_with_retry(
    gateway: LlmGateway,
    request: StructuredGenerationRequest,
    *,
    attempts: int,
    backoff_seconds: float,
    retry_timeouts: bool,
    on_retry: RetryReporter | None = None,
    truncation_retry_max_tokens: int | None = None,
    retry_on_truncation: bool = True,
):
    """Retry transient failures and one truncated response with a larger budget."""
    active_request = request
    transient_attempt = 1
    truncation_retried = False
    while True:
        try:
            return gateway.generate_structured(active_request)
        except LlmResponseError as error:
            can_retry_truncation = (
                retry_on_truncation
                and not truncation_retried
                and error.finish_reason == "length"
                and truncation_retry_max_tokens is not None
                and (active_request.max_tokens or 0) < truncation_retry_max_tokens
            )
            if not can_retry_truncation:
                raise
            truncation_retried = True
            active_request = replace(
                active_request,
                max_tokens=truncation_retry_max_tokens,
                reasoning_enabled=False,
            )
            if on_retry is not None:
                on_retry(transient_attempt, error)
        except LlmUnavailableError as error:
            if isinstance(error, LlmTimeoutError) and not retry_timeouts:
                raise
            if transient_attempt >= attempts:
                raise
            if on_retry is not None:
                on_retry(transient_attempt, error)
            if backoff_seconds:
                time.sleep(backoff_seconds * transient_attempt)
            transient_attempt += 1
