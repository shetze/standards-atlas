"""Configuration for the read-only Standards Atlas MCP adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class McpExposureConfig(BaseModel):
    """Control which corpus details may leave the application boundary."""

    model_config = ConfigDict(frozen=True)
    clause_text: bool = True
    source_paths: bool = False
    internal_metadata: bool = False


class McpCapabilityConfig(BaseModel):
    """Explicitly enabled mutating MCP capabilities."""

    model_config = ConfigDict(frozen=True)
    formula_transcription: bool = False


class McpLimitConfig(BaseModel):
    """Upper bounds applied to all externally supplied MCP requests."""

    model_config = ConfigDict(frozen=True)
    max_results: int = Field(default=20, ge=1, le=1000)
    max_sample_size: int = Field(default=50, ge=1, le=1000)
    max_clause_characters: int = Field(default=20_000, ge=1)
    max_request_body_bytes: int = Field(default=4 * 1024 * 1024, ge=1024)


class McpHttpConfig(BaseModel):
    """Streamable HTTP listener and browser-origin policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65_535)
    path: str = "/mcp"
    allowed_hosts: tuple[str, ...] = ("localhost:*", "127.0.0.1:*")
    allowed_origins: tuple[str, ...] = (
        "http://localhost:*",
        "http://127.0.0.1:*",
    )
    stateless: bool = True

    @model_validator(mode="after")
    def validate_path(self) -> McpHttpConfig:
        if not self.path.startswith("/"):
            raise ValueError("http.path must start with '/'")
        return self


class McpAuthConfig(BaseModel):
    """Bearer-token policy for remote operation."""

    model_config = ConfigDict(frozen=True)
    enabled: bool = False
    token_environment_variable: str = "STANDARDS_ATLAS_MCP_TOKEN"


class McpAuditConfig(BaseModel):
    """Structured JSON-lines request audit configuration."""

    model_config = ConfigDict(frozen=True)
    enabled: bool = True
    path: Path = Path("local/logs/mcp-audit.jsonl")


class McpProcessConfig(BaseModel):
    """Files and timeouts used to manage the background MCP process."""

    model_config = ConfigDict(frozen=True)
    state_directory: Path = Path(".atlas/work/mcp")
    startup_timeout_seconds: float = Field(default=15.0, gt=0)
    shutdown_timeout_seconds: float = Field(default=10.0, gt=0)
    health_timeout_seconds: float = Field(default=0.5, gt=0)

    @property
    def pid_file(self) -> Path:
        return self.state_directory / "server.pid"

    @property
    def log_file(self) -> Path:
        return self.state_directory / "server.log"


class McpServerConfig(BaseModel):
    """Runtime configuration for the MCP inbound adapter."""

    model_config = ConfigDict(frozen=True)
    name: str = Field(default="standards-atlas", min_length=1)
    transport: Literal["stdio", "streamable-http"] = "stdio"
    workspace: Path = Path(".atlas/data")
    allowed_document_keys: tuple[str, ...] = ()
    limits: McpLimitConfig = McpLimitConfig()
    expose: McpExposureConfig = McpExposureConfig()
    capabilities: McpCapabilityConfig = McpCapabilityConfig()
    http: McpHttpConfig = McpHttpConfig()
    auth: McpAuthConfig = McpAuthConfig()
    audit: McpAuditConfig = McpAuditConfig()
    process: McpProcessConfig = McpProcessConfig()

    @model_validator(mode="after")
    def validate_remote_configuration(self) -> McpServerConfig:
        if self.transport == "streamable-http":
            public = self.http.host not in {"127.0.0.1", "localhost", "::1"}
            if public and not self.auth.enabled:
                raise ValueError("authentication is required when binding MCP beyond localhost")
        return self

    @classmethod
    def load(cls, path: Path) -> McpServerConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError("MCP configuration must be a YAML mapping")
        return cls.model_validate(payload.get("mcp", payload))
