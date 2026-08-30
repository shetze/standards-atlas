"""Configuration for OpenAI-compatible local inference endpoints."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class LlmRuntime(StrEnum):
    """Inference runtimes supported by the managed RamaLama server."""

    LLAMA_CPP = "llama.cpp"
    VLLM = "vllm"


@dataclass(frozen=True)
class RamaLamaServerConfig:
    """Lifecycle configuration for the project-owned RamaLama server."""

    enabled: bool = True
    name: str = "standards-atlas-llm"
    model: str = "granite"
    runtime: LlmRuntime = LlmRuntime.LLAMA_CPP
    startup_timeout_seconds: float = 120.0
    shutdown_timeout_seconds: float = 30.0
    executable: str = "ramalama"
    backend: str = "auto"
    selinux: bool = False
    state_directory: Path = Path(".atlas/work/llm/runtime")
    ownership_file: Path = Path(".atlas/work/llm/active-runtime.json")

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("llm.server.name must not be empty")
        if not self.model.strip():
            raise ValueError("llm.server.model must not be empty")
        if self.startup_timeout_seconds <= 0:
            raise ValueError("llm.server.startup_timeout_seconds must be positive")
        if self.shutdown_timeout_seconds <= 0:
            raise ValueError("llm.server.shutdown_timeout_seconds must be positive")
        if not self.executable.strip():
            raise ValueError("llm.server.executable must not be empty")
        if not self.backend.strip():
            raise ValueError("llm.server.backend must not be empty")

    @property
    def pid_file(self) -> Path:
        """PID file used by the managed foreground RamaLama process."""
        return self.state_directory / "ramalama.pid"

    @property
    def log_file(self) -> Path:
        """Combined stdout/stderr log of the managed RamaLama process."""
        return self.state_directory / "ramalama.log"


@dataclass(frozen=True)
class LlmConfig:
    """Provider-independent endpoint and managed-server configuration."""

    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "granite"
    timeout_seconds: float = 120.0
    api_key: str | None = None
    cache_directory: Path | None = Path(".atlas/cache/llm")
    server: RamaLamaServerConfig = RamaLamaServerConfig()

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("llm.base_url must use http or https")
        if not self.model.strip():
            raise ValueError("llm.model must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("llm.timeout_seconds must be positive")

    @classmethod
    def load(cls, path: Path | None = None) -> LlmConfig:
        """Load YAML configuration and apply ``STANDARDS_ATLAS_LLM_*`` overrides."""
        config = cls()
        if path is not None:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            config = cls.from_mapping(_mapping(payload).get("llm", payload))

        overrides: dict[str, Any] = {}
        environment = os.environ
        if value := environment.get("STANDARDS_ATLAS_LLM_BASE_URL"):
            overrides["base_url"] = value
        if value := environment.get("STANDARDS_ATLAS_LLM_MODEL"):
            overrides["model"] = value
        if value := environment.get("STANDARDS_ATLAS_LLM_TIMEOUT_SECONDS"):
            overrides["timeout_seconds"] = float(value)
        if value := environment.get("STANDARDS_ATLAS_LLM_API_KEY"):
            overrides["api_key"] = value
        if "STANDARDS_ATLAS_LLM_CACHE_DIRECTORY" in environment:
            value = environment["STANDARDS_ATLAS_LLM_CACHE_DIRECTORY"]
            overrides["cache_directory"] = Path(value) if value else None
        return replace(config, **overrides)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> LlmConfig:
        cache_value = payload.get("cache_directory", ".atlas/cache/llm")
        model = str(payload.get("model", cls.model))
        server_payload = _mapping(payload.get("server", {}))
        server = RamaLamaServerConfig(
            enabled=bool(server_payload.get("enabled", True)),
            name=str(server_payload.get("name", "standards-atlas-llm")),
            model=str(server_payload.get("model", model)),
            runtime=LlmRuntime(str(server_payload.get("runtime", LlmRuntime.LLAMA_CPP))),
            startup_timeout_seconds=float(server_payload.get("startup_timeout_seconds", 120)),
            shutdown_timeout_seconds=float(server_payload.get("shutdown_timeout_seconds", 30)),
            executable=str(server_payload.get("executable", "ramalama")),
            backend=str(server_payload.get("backend", "auto")),
            selinux=bool(server_payload.get("selinux", False)),
            state_directory=Path(
                str(server_payload.get("state_directory", ".atlas/work/llm/runtime"))
            ),
            ownership_file=Path(
                str(server_payload.get("ownership_file", ".atlas/work/llm/active-runtime.json"))
            ),
        )
        return cls(
            base_url=str(payload.get("base_url", cls.base_url)),
            model=model,
            timeout_seconds=float(payload.get("timeout_seconds", cls.timeout_seconds)),
            api_key=(str(payload["api_key"]) if payload.get("api_key") else None),  # notsecret
            cache_directory=Path(str(cache_value)) if cache_value else None,
            server=server,
        )


@dataclass(frozen=True)
class ContextEnrichmentConfig:
    """Task-specific runtime configuration for CBox context enrichment."""

    prompt_task: str = "context-routing-enrichment"
    prompt_version: str = "context-routing-v1"
    max_tokens: int = 1024
    retry_max_tokens: int = 2048
    llm: LlmConfig = LlmConfig()

    def __post_init__(self) -> None:
        if not self.prompt_task.strip():
            raise ValueError("context_enrichment.prompt.task must not be empty")
        if not self.prompt_version.strip():
            raise ValueError("context_enrichment.prompt.version must not be empty")
        if self.max_tokens <= 0:
            raise ValueError("context_enrichment.generation.max_tokens must be positive")
        if self.retry_max_tokens < self.max_tokens:
            raise ValueError("context_enrichment.generation.retry_max_tokens must be >= max_tokens")

    @classmethod
    def load(cls, path: Path) -> ContextEnrichmentConfig:
        """Load task settings plus the dedicated LLM runtime from one YAML file."""
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        root = _mapping(payload)
        task = _mapping(root.get("context_enrichment", {}))
        prompt = _mapping(task.get("prompt", {}))
        generation = _mapping(task.get("generation", {}))
        return cls(
            prompt_task=str(prompt.get("task", cls.prompt_task)),
            prompt_version=str(prompt.get("version", cls.prompt_version)),
            max_tokens=int(generation.get("max_tokens", cls.max_tokens)),
            retry_max_tokens=int(generation.get("retry_max_tokens", cls.retry_max_tokens)),
            llm=LlmConfig.load(path),
        )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("LLM configuration must be a YAML mapping")
    return value
