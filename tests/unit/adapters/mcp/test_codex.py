import tomllib
from pathlib import Path

import pytest

from standards_atlas.adapters.mcp.codex import CodexMcpConfig


def test_renders_token_free_codex_configuration() -> None:
    rendered = CodexMcpConfig(url="http://192.168.0.77:8765/mcp").render_toml()

    assert "[mcp_servers.standards-atlas]" in rendered
    assert 'url = "http://192.168.0.77:8765/mcp/"' in rendered
    assert 'bearer_token_env_var = "STANDARDS_ATLAS_MCP_TOKEN"' in rendered
    assert "list_standards" in rendered
    assert "Bearer" not in rendered


def test_builds_official_codex_registration_command() -> None:
    command = CodexMcpConfig(url="https://atlas.example/mcp/").codex_add_command()

    assert command == (
        "codex",
        "mcp",
        "add",
        "standards-atlas",
        "--url",
        "https://atlas.example/mcp/",
        "--bearer-token-env-var",
        "STANDARDS_ATLAS_MCP_TOKEN",
    )


def test_rejects_unsafe_names_and_urls() -> None:
    with pytest.raises(ValueError, match="http"):
        CodexMcpConfig(url="file:///tmp/mcp")
    with pytest.raises(ValueError, match="server name"):
        CodexMcpConfig(url="https://atlas.example/mcp", server_name="bad.name")
    with pytest.raises(ValueError, match="environment variable"):
        CodexMcpConfig(url="https://atlas.example/mcp", bearer_token_env_var="BAD-NAME")


def test_write_refuses_to_replace_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    config = CodexMcpConfig(url="https://atlas.example/mcp")

    config.write(target)
    with pytest.raises(FileExistsError):
        config.write(target)
    config.write(target, overwrite=True)

    assert target.read_text(encoding="utf-8") == config.render_toml()


def test_review_tool_allowlist_requires_explicit_opt_in() -> None:
    from standards_atlas.adapters.mcp.codex import REVIEW_PREPARATION_TOOLS
    from standards_atlas.adapters.mcp.compatibility import REQUIRED_TOOLS

    def tools(config):
        server = tomllib.loads(config.render_toml())["mcp_servers"]["standards-atlas"]
        return server["enabled_tools"]

    default = tools(CodexMcpConfig(url="http://localhost:8765/mcp"))
    enabled = tools(CodexMcpConfig(url="http://localhost:8765/mcp", review_preparation=True))
    assert tuple(default) == REQUIRED_TOOLS
    assert tuple(enabled) == ("get_server_info", *REVIEW_PREPARATION_TOOLS)
    assert "get_clause" not in enabled
    assert len(enabled) == len(set(enabled))
    assert not any("confirm" in name or "publish" in name for name in enabled)
