"""Factories for managed local runtime processes used by CLI commands."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.llm import LlmConfig, RamaLamaServerManager
from standards_atlas.adapters.mcp import McpServerConfig, McpServerProcessManager


def managed_llm_server(config: Path) -> RamaLamaServerManager:
    """Build the managed RamaLama server configured by ``config``."""
    return RamaLamaServerManager(LlmConfig.load(config))


def managed_mcp_server(config: Path) -> McpServerProcessManager:
    """Build the managed MCP server configured by ``config``."""
    return McpServerProcessManager(McpServerConfig.load(config), config)
