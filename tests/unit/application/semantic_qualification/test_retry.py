from standards_atlas.application.ports.llm_gateway import (
    LlmHealth,
    LlmUnavailableError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from standards_atlas.application.semantic_qualification.retry import generate_with_retry


class Gateway:
    def __init__(self) -> None:
        self.calls = 0

    def health(self) -> LlmHealth:
        return LlmHealth(True, ("model",))

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        self.calls += 1
        if self.calls == 1:
            raise LlmUnavailableError("temporary")
        return StructuredGenerationResult(
            value={},
            model=request.model or "model",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="input",
            raw_response_hash="response",
            duration_ms=1,
            raw_response={},
        )


def test_retries_transient_generation_failure() -> None:
    gateway = Gateway()
    request = StructuredGenerationRequest(
        task="task",
        system_prompt="system",
        user_prompt="user",
        output_schema={"type": "object"},
        prompt_version="v1",
        model="model",
    )

    result = generate_with_retry(
        gateway,
        request,
        attempts=2,
        backoff_seconds=0,
        retry_timeouts=True,
    )

    assert result.provider == "fake"
    assert gateway.calls == 2
