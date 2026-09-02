"""Serve local interactive chat services."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.web import (
    PromptWorkbenchHttpConfig,
    run_prompt_workbench_server,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import chat_app
from standards_atlas.cli.composition import build_prompt_workbench_web_app


class ChatServiceType(StrEnum):
    """Registered local chat-service implementations."""

    PROMPT_WORKBENCH = "prompt-workbench"


@chat_app.command("serve")
def serve_chat_service(
    service: Annotated[
        ChatServiceType,
        typer.Option(
            "--service",
            "--service-type",
            case_sensitive=False,
            help="Local chat-service implementation to start.",
        ),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Persisted EngineeringDocument workspace."),
    ] = cli_defaults.DEFAULT_WORKSPACE,
    llm_config: Annotated[
        Path,
        typer.Option("--llm-config", exists=True, readable=True, help="LLM YAML configuration."),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    manifest_directory: Annotated[
        Path,
        typer.Option(
            "--manifest-directory",
            exists=True,
            file_okay=False,
            readable=True,
            help="Directory containing qualification manifests.",
        ),
    ] = cli_defaults.DEFAULT_MANIFEST_DIRECTORY,
    host: Annotated[
        str,
        typer.Option("--host", help="Loopback interface used by the local service."),
    ] = cli_defaults.DEFAULT_CHAT_HOST,
    port: Annotated[
        int,
        typer.Option("--port", min=1, max=65_535, help="Local HTTP port."),
    ] = cli_defaults.DEFAULT_CHAT_PORT,
) -> None:
    """Run one explicitly selected local chat service in the foreground."""
    try:
        http_config = PromptWorkbenchHttpConfig(host=host, port=port)
        if service is ChatServiceType.PROMPT_WORKBENCH:
            web_app = build_prompt_workbench_web_app(
                workspace=workspace,
                llm_config_path=llm_config,
                manifest_directory=manifest_directory,
                http_config=http_config,
            )
            typer.echo(f"Prompt workbench available at http://{host}:{port}")
            run_prompt_workbench_server(web_app, http_config)
            return
        raise ValueError(f"unsupported chat service: {service}")
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
