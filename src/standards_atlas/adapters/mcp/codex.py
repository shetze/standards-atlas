"""Codex configuration support for the Standards Atlas MCP server."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from standards_atlas.adapters.mcp.compatibility import REQUIRED_TOOLS

_SERVER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_ENVIRONMENT_VARIABLE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class CodexMcpConfig:
    """Safe Codex client configuration for a remote Standards Atlas server."""

    url: str
    server_name: str = "standards-atlas"
    bearer_token_env_var: str = "STANDARDS_ATLAS_MCP_TOKEN"
    startup_timeout_sec: int = 10
    tool_timeout_sec: int = 60
    required: bool = True

    def __post_init__(self) -> None:
        if not self.url.startswith(("http://", "https://")):
            raise ValueError("Codex MCP URL must use http:// or https://")
        if not _SERVER_NAME_PATTERN.fullmatch(self.server_name):
            raise ValueError("Codex MCP server name may contain letters, digits, '-' and '_'")
        if not _ENVIRONMENT_VARIABLE_PATTERN.fullmatch(self.bearer_token_env_var):
            raise ValueError("bearer token environment variable has an invalid name")
        if self.startup_timeout_sec <= 0 or self.tool_timeout_sec <= 0:
            raise ValueError("Codex MCP timeouts must be positive")

    @property
    def normalized_url(self) -> str:
        return self.url if self.url.endswith("/") else f"{self.url}/"

    def render_toml(self) -> str:
        """Render a token-free Codex config.toml fragment."""
        tools = ", ".join(f'"{tool}"' for tool in REQUIRED_TOOLS)
        required = str(self.required).lower()
        return (
            f"[mcp_servers.{self.server_name}]\n"
            f'url = "{_escape_toml(self.normalized_url)}"\n'
            f'bearer_token_env_var = "{self.bearer_token_env_var}"\n'
            f"startup_timeout_sec = {self.startup_timeout_sec}\n"
            f"tool_timeout_sec = {self.tool_timeout_sec}\n"
            f"required = {required}\n"
            'default_tools_approval_mode = "auto"\n'
            f"enabled_tools = [{tools}]\n"
        )

    def codex_add_command(self) -> tuple[str, ...]:
        """Return the equivalent official Codex CLI registration command."""
        return (
            "codex",
            "mcp",
            "add",
            self.server_name,
            "--url",
            self.normalized_url,
            "--bearer-token-env-var",
            self.bearer_token_env_var,
        )

    def write(self, target: Path, *, overwrite: bool = False) -> Path:
        """Write the config fragment without ever resolving the token value."""
        if target.exists() and not overwrite:
            raise FileExistsError(f"refusing to overwrite existing file: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render_toml(), encoding="utf-8")
        return target


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
