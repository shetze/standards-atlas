"""Command-line interface for Standards Atlas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.llm import (
    RamaLamaServerError,
)
from standards_atlas.adapters.mcp import (
    CodexMcpConfig,
    McpCompatibilityProbe,
    McpServerConfig,
    McpServerProcessError,
    StreamableHttpJsonRpcTransport,
    run_mcp_server,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import (
    llm_app,
    mcp_app,
)
from standards_atlas.cli.runtime_managers import (
    managed_llm_server,
    managed_mcp_server,
)


@llm_app.command("start")
def start_llm_server(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="LLM YAML configuration."),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
) -> None:
    try:
        managed_llm_server(config).start()
    except (OSError, ValueError, RamaLamaServerError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("RamaLama server started.")


@llm_app.command("stop")
def stop_llm_server(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="LLM YAML configuration."),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
) -> None:
    try:
        managed_llm_server(config).stop()
    except (OSError, ValueError, RamaLamaServerError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("RamaLama server stopped.")


@llm_app.command("status")
def show_llm_server_status(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="LLM YAML configuration."),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
) -> None:
    try:
        status = managed_llm_server(config).status()
    except (OSError, ValueError, RamaLamaServerError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("running" if status.running else "stopped")
    if status.detail:
        typer.echo(status.detail)


@mcp_app.command("start")
def start_mcp(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="MCP YAML configuration."),
    ] = cli_defaults.DEFAULT_MCP_CONFIG,
) -> None:
    """Start the MCP HTTP server as a managed background process."""
    try:
        managed_mcp_server(config).start()
    except (OSError, RuntimeError, ValueError, McpServerProcessError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("MCP server started.")


@mcp_app.command("stop")
def stop_mcp(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="MCP YAML configuration."),
    ] = cli_defaults.DEFAULT_MCP_CONFIG,
) -> None:
    """Stop the managed MCP background process."""
    try:
        managed_mcp_server(config).stop()
    except (OSError, RuntimeError, ValueError, McpServerProcessError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("MCP server stopped.")


@mcp_app.command("status")
def show_mcp_status(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="MCP YAML configuration."),
    ] = cli_defaults.DEFAULT_MCP_CONFIG,
) -> None:
    """Show process and endpoint status for the managed MCP server."""
    try:
        status = managed_mcp_server(config).status()
    except (OSError, RuntimeError, ValueError, McpServerProcessError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("running" if status.running else "stopped")
    if status.pid is not None:
        typer.echo(f"pid: {status.pid}")
    if status.detail:
        typer.echo(status.detail)


@mcp_app.command("serve")
def serve_mcp(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, readable=True, help="MCP YAML configuration."),
    ] = cli_defaults.DEFAULT_MCP_CONFIG,
) -> None:
    """Run the read-only MCP server in the foreground."""
    try:
        run_mcp_server(McpServerConfig.load(config))
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


@mcp_app.command("probe")
def probe_mcp(
    url: Annotated[str, typer.Option("--url", help="Streamable HTTP MCP endpoint.")],
    token_environment_variable: Annotated[
        str,
        typer.Option(
            "--token-env",
            help="Environment variable containing the bearer token.",
        ),
    ] = cli_defaults.DEFAULT_MCP_TOKEN_ENVIRONMENT_VARIABLE,
    timeout_seconds: Annotated[
        float,
        typer.Option("--timeout", min=0.1, help="HTTP timeout in seconds."),
    ] = cli_defaults.DEFAULT_MCP_TIMEOUT_SECONDS,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional JSON report path."),
    ] = cli_defaults.DEFAULT_NONE,
) -> None:
    """Run an interoperable MCP handshake and read-only contract probe."""
    import os

    token = os.environ.get(token_environment_variable)
    transport = StreamableHttpJsonRpcTransport(
        url,
        bearer_token=token,
        timeout_seconds=timeout_seconds,
    )
    try:
        report = McpCompatibilityProbe(transport).run()
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    payload = report.as_dict()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{rendered}\n", encoding="utf-8")
    typer.echo(rendered)
    if not report.passed:
        raise typer.Exit(code=1)


@mcp_app.command("codex-config")
def render_codex_mcp_config(
    url: Annotated[str, typer.Option("--url", help="Streamable HTTP MCP endpoint.")],
    server_name: Annotated[
        str,
        typer.Option("--name", help="Codex MCP server name."),
    ] = cli_defaults.DEFAULT_MCP_SERVER_NAME,
    token_environment_variable: Annotated[
        str,
        typer.Option(
            "--token-env",
            help="Environment variable containing the bearer token.",
        ),
    ] = cli_defaults.DEFAULT_MCP_TOKEN_ENVIRONMENT_VARIABLE,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional config fragment path."),
    ] = cli_defaults.DEFAULT_NONE,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace an existing output file."),
    ] = cli_defaults.DEFAULT_FALSE,
) -> None:
    """Render a secure Codex Streamable HTTP MCP configuration fragment."""
    try:
        config = CodexMcpConfig(
            url=url,
            server_name=server_name,
            bearer_token_env_var=token_environment_variable,
        )
        if output is not None:
            config.write(output, overwrite=overwrite)
    except (FileExistsError, OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(config.render_toml())
    typer.echo("Equivalent registration command:", err=True)
    typer.echo(" ".join(config.codex_add_command()), err=True)
