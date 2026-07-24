"""Configuration for OpenAI-compatible local inference endpoints."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class LlmConfig:
    """Runtime configuration independent from RamaLama container management."""

    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "granite"
    timeout_seconds: float = 120.0
    api_key: str | None = None
    cache_directory: Path | None = Path(".atlas/llm/cache")

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
        cache_value = payload.get("cache_directory", ".atlas/llm/cache")
        return cls(
            base_url=str(payload.get("base_url", cls.base_url)),
            model=str(payload.get("model", cls.model)),
            timeout_seconds=float(payload.get("timeout_seconds", cls.timeout_seconds)),
            api_key=(str(payload["api_key"]) if payload.get("api_key") else None),
            cache_directory=Path(str(cache_value)) if cache_value else None,
        )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("LLM configuration must be a YAML mapping")
    return value
