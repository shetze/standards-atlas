"""Configuration for the Standards Atlas MCP adapter."""

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
    review_preparation: bool = False


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


class McpReviewConfig(BaseModel):
    """Explicit local package registry. Holdout assistance is separately opt-in."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    enabled: bool = False
    workspace: Path = Path("local/review/partial-semantic")
    allow_holdout_assistance: bool = False


class McpAp03DevelopmentConfig(BaseModel):
    """Server-owned AP03 optimizer scope; client tool allowlists are only an extra fence."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    review_handles: tuple[str, ...] = ()
    experiment_ids: tuple[str, ...] = ()
    project_root: Path = Path(".")
    staging_directory: Path = Path("local/evaluation/assertions/ap03/codex-staging")
    allowed_data_routes: tuple[str, ...] = ("local-private-context-source-packages",)
    max_prompt_characters: int = Field(default=24_000, ge=256, le=200_000)

    @model_validator(mode="after")
    def validate_scope(self) -> McpAp03DevelopmentConfig:
        if not self.review_handles:
            raise ValueError("AP03 development profile requires at least one review handle")
        for value in (*self.review_handles, *self.experiment_ids):
            if not value or "/" in value or "\\" in value or value in {".", ".."}:
                raise ValueError(
                    "AP03 development handles/experiment ids must be safe path components"
                )
        if not self.allowed_data_routes:
            raise ValueError("AP03 development profile requires an explicit data-route allowlist")
        return self


class McpServerConfig(BaseModel):
    """Runtime configuration for the MCP inbound adapter."""

    model_config = ConfigDict(frozen=True)
    name: str = Field(default="standards-atlas", min_length=1)
    transport: Literal["stdio", "streamable-http"] = "stdio"
    profile: Literal["general", "ap03-development"] = "general"
    workspace: Path = Path(".atlas/data")
    allowed_document_keys: tuple[str, ...] = ()
    limits: McpLimitConfig = McpLimitConfig()
    expose: McpExposureConfig = McpExposureConfig()
    capabilities: McpCapabilityConfig = McpCapabilityConfig()
    http: McpHttpConfig = McpHttpConfig()
    auth: McpAuthConfig = McpAuthConfig()
    audit: McpAuditConfig = McpAuditConfig()
    process: McpProcessConfig = McpProcessConfig()
    review: McpReviewConfig = McpReviewConfig()
    ap03_development: McpAp03DevelopmentConfig | None = None

    @model_validator(mode="after")
    def validate_remote_configuration(self) -> McpServerConfig:
        if self.transport == "streamable-http":
            public = self.http.host not in {"127.0.0.1", "localhost", "::1"}
            if public and not self.auth.enabled:
                raise ValueError("authentication is required when binding MCP beyond localhost")
        if self.profile == "ap03-development":
            if self.ap03_development is None:
                raise ValueError("AP03 development profile requires ap03_development configuration")
            if not self.allowed_document_keys:
                raise ValueError("AP03 development profile requires a non-empty document allowlist")
            if not self.review.enabled:
                raise ValueError("AP03 development profile requires the assertion review registry")
            if self.review.allow_holdout_assistance:
                raise ValueError("AP03 development profile cannot enable holdout assistance")
            if not self.expose.clause_text:
                raise ValueError(
                    "AP03 development review requires explicit Development text exposure"
                )
            if self.expose.source_paths:
                raise ValueError("AP03 development profile cannot expose source filesystem paths")
            if self.capabilities.formula_transcription:
                raise ValueError("AP03 development profile cannot enable formula transcription")
            if self.capabilities.review_preparation:
                raise ValueError(
                    "AP03 development profile uses task-specific read-only review; "
                    "legacy model-review preparation must stay disabled"
                )
        elif self.ap03_development is not None:
            raise ValueError("ap03_development configuration requires profile='ap03-development'")
        return self

    @property
    def is_ap03_development(self) -> bool:
        return self.profile == "ap03-development"

    @classmethod
    def load(cls, path: Path) -> McpServerConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError("MCP configuration must be a YAML mapping")
        return cls.model_validate(payload.get("mcp", payload))
