"""Adapters for local OpenAI-compatible LLM inference."""

from standards_atlas.adapters.llm.codex_cli import CodexCliConfig, CodexCliLlmGateway
from standards_atlas.adapters.llm.config import (
    ContextEnrichmentConfig,
    LlmConfig,
    LlmRuntime,
    RamaLamaServerConfig,
)
from standards_atlas.adapters.llm.formal_semantic_extractor import OntologyGuidedLlmExtractor
from standards_atlas.adapters.llm.managed_ramalama import ManagedRamaLamaGateway
from standards_atlas.adapters.llm.openai_compatible import (
    LlmGatewayError,
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
    OpenAICompatibleLlmGateway,
)
from standards_atlas.adapters.llm.ramalama_server import (
    RamaLamaServerError,
    RamaLamaServerManager,
    RamaLamaServerStatus,
)

__all__ = [
    "CodexCliConfig",
    "CodexCliLlmGateway",
    "ContextEnrichmentConfig",
    "LlmConfig",
    "LlmRuntime",
    "LlmGatewayError",
    "LlmResponseError",
    "LlmTimeoutError",
    "LlmUnavailableError",
    "ManagedRamaLamaGateway",
    "OpenAICompatibleLlmGateway",
    "OntologyGuidedLlmExtractor",
    "RamaLamaServerConfig",
    "RamaLamaServerError",
    "RamaLamaServerManager",
    "RamaLamaServerStatus",
]
