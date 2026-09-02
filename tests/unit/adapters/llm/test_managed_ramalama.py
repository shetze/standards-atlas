from __future__ import annotations

from standards_atlas.adapters.llm.config import LlmConfig, RamaLamaServerConfig
from standards_atlas.adapters.llm.managed_ramalama import ManagedRamaLamaGateway
from standards_atlas.adapters.llm.ramalama_server import RamaLamaServerStatus
from standards_atlas.application.ports.llm_gateway import (
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


def _config() -> LlmConfig:
    return LlmConfig(
        model="initial",
        server=RamaLamaServerConfig(model="initial"),
    )


def test_activation_switches_the_project_owned_runtime(monkeypatch) -> None:
    events: list[tuple[str, str]] = []
    active = {"model": "old-model"}

    class Manager:
        def __init__(self, config):
            self.config = config

        def status(self):
            running = active["model"] == self.config.server.model
            return RamaLamaServerStatus(running, models=(active["model"],))

        def stop(self):
            events.append(("stop", self.config.server.model))
            active["model"] = ""

        def start(self):
            events.append(("start", self.config.server.model))
            active["model"] = self.config.server.model

    monkeypatch.setattr(
        "standards_atlas.adapters.llm.managed_ramalama.RamaLamaServerManager", Manager
    )

    status = ManagedRamaLamaGateway(_config()).activate("new-model")

    assert status.running is True
    assert events == [("stop", "initial"), ("start", "new-model")]


def test_generation_activates_selected_model_and_disables_cache_by_default(monkeypatch) -> None:
    active = {"model": ""}
    gateway_configs = []

    class Manager:
        def __init__(self, config):
            self.config = config

        def status(self):
            return RamaLamaServerStatus(active["model"] == self.config.server.model)

        def stop(self):
            active["model"] = ""

        def start(self):
            active["model"] = self.config.server.model

    class Gateway:
        provider = "test"

        def __init__(self, config):
            gateway_configs.append(config)

        def generate_structured(self, request):
            assert active["model"] == request.model
            return StructuredGenerationResult(
                value={"ok": True},
                model=request.model or "",
                provider="test",
                prompt_version=request.prompt_version,
                input_hash="input",
                raw_response_hash="response",
                duration_ms=1,
            )

    monkeypatch.setattr(
        "standards_atlas.adapters.llm.managed_ramalama.RamaLamaServerManager", Manager
    )
    monkeypatch.setattr(
        "standards_atlas.adapters.llm.managed_ramalama.OpenAICompatibleLlmGateway", Gateway
    )
    request = StructuredGenerationRequest(
        task="test",
        system_prompt="system",
        user_prompt="user",
        output_schema={"type": "object"},
        prompt_version="1",
        model="selected",
    )

    ManagedRamaLamaGateway(_config()).generate_structured(request)

    assert gateway_configs[-1].model == "selected"
    assert gateway_configs[-1].server.model == "selected"
    assert gateway_configs[-1].cache_directory is None


def test_generation_preserves_configured_cache_when_explicitly_enabled(monkeypatch) -> None:
    gateway_configs = []

    class Manager:
        def __init__(self, config):
            self.config = config

        def status(self):
            return RamaLamaServerStatus(True)

    class Gateway:
        provider = "test"

        def __init__(self, config):
            gateway_configs.append(config)

        def generate_structured(self, request):
            return StructuredGenerationResult(
                value={},
                model="selected",
                provider="test",
                prompt_version="1",
                input_hash="input",
                raw_response_hash="response",
                duration_ms=1,
            )

    monkeypatch.setattr(
        "standards_atlas.adapters.llm.managed_ramalama.RamaLamaServerManager", Manager
    )
    monkeypatch.setattr(
        "standards_atlas.adapters.llm.managed_ramalama.OpenAICompatibleLlmGateway", Gateway
    )
    request = StructuredGenerationRequest(
        task="test",
        system_prompt="system",
        user_prompt="user",
        output_schema={"type": "object"},
        prompt_version="1",
        model="selected",
        metadata={"use_cache": True},
    )

    ManagedRamaLamaGateway(_config()).generate_structured(request)

    assert gateway_configs[-1].cache_directory == _config().cache_directory
