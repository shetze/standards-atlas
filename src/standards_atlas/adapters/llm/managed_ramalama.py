"""Serialized model activation and generation for an interactive RamaLama client."""

from __future__ import annotations

from dataclasses import replace
from threading import RLock

from standards_atlas.adapters.llm.config import LlmConfig
from standards_atlas.adapters.llm.openai_compatible import OpenAICompatibleLlmGateway
from standards_atlas.adapters.llm.ramalama_server import (
    RamaLamaServerManager,
    RamaLamaServerStatus,
)
from standards_atlas.application.ports.llm_gateway import (
    LlmHealth,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


class ManagedRamaLamaGateway:
    """Keep RamaLama model switches and requests inside one critical section.

    RamaLama serves one model at the configured endpoint.  A workbench can select
    a different model for every experiment, so activation and inference must be
    serialized to prevent one request from changing the runtime below another.
    """

    provider = OpenAICompatibleLlmGateway.provider

    def __init__(self, config: LlmConfig) -> None:
        self._base_config = config
        self._lock = RLock()

    def health(self) -> LlmHealth:
        with self._lock:
            return OpenAICompatibleLlmGateway(self._base_config).health()

    def activate(self, model_ref: str) -> RamaLamaServerStatus:
        """Activate a model, stopping only a project-owned previous runtime."""
        if not model_ref.strip():
            raise ValueError("RamaLama model reference must not be empty")
        with self._lock:
            return self._activate_locked(model_ref)

    def generate_structured(
        self,
        request: StructuredGenerationRequest,
    ) -> StructuredGenerationResult:
        model_ref = request.model or self._base_config.model
        use_cache = bool(request.metadata.get("use_cache", False))
        with self._lock:
            self._activate_locked(model_ref)
            config = self._config_for_model(model_ref)
            if not use_cache:
                config = replace(config, cache_directory=None)
            return OpenAICompatibleLlmGateway(config).generate_structured(request)

    def _activate_locked(self, model_ref: str) -> RamaLamaServerStatus:
        config = self._config_for_model(model_ref)
        manager = RamaLamaServerManager(config)
        status = manager.status()
        if status.running:
            return status

        # The base manager uses the shared ownership record and therefore stops
        # only a runtime previously started by this project.
        RamaLamaServerManager(self._base_config).stop()
        manager.start()
        return manager.status()

    def _config_for_model(self, model_ref: str) -> LlmConfig:
        return replace(
            self._base_config,
            model=model_ref,
            server=replace(self._base_config.server, model=model_ref),
        )
