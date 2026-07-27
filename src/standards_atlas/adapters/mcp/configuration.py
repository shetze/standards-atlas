"""Configuration for the read-only Standards Atlas MCP adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class McpExposureConfig(BaseModel):
    """Control which corpus details may leave the application boundary."""

    model_config = ConfigDict(frozen=True)

    clause_text: bool = True
    source_paths: bool = False
    internal_metadata: bool = False


class McpLimitConfig(BaseModel):
    """Upper bounds applied to all externally supplied MCP requests."""

    model_config = ConfigDict(frozen=True)

    max_results: int = Field(default=20, ge=1, le=1000)
    max_sample_size: int = Field(default=50, ge=1, le=1000)
    max_clause_characters: int = Field(default=20_000, ge=1)


class McpServerConfig(BaseModel):
    """Runtime configuration for the MCP inbound adapter."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(default="standards-atlas", min_length=1)
    transport: Literal["stdio"] = "stdio"
    workspace: Path = Path(".atlas")
    allowed_document_keys: tuple[str, ...] = ()
    limits: McpLimitConfig = McpLimitConfig()
    expose: McpExposureConfig = McpExposureConfig()

    @classmethod
    def load(cls, path: Path) -> McpServerConfig:
        """Load configuration from YAML."""
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError("MCP configuration must be a YAML mapping")
        return cls.model_validate(payload.get("mcp", payload))
