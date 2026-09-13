"""Serve local interactive chat services."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from standards_atlas.adapters.web import (
    PromptWorkbenchHttpConfig,
    ReviewWorkbenchHttpConfig,
    run_prompt_workbench_server,
    run_review_workbench_server,
)
from standards_atlas.cli import defaults as cli_defaults
from standards_atlas.cli.apps import chat_app
from standards_atlas.cli.composition import (
    build_prompt_workbench_web_app,
    build_review_workbench_web_app,
)


class ChatServiceType(StrEnum):
    """Registered local chat-service implementations."""

    PROMPT_WORKBENCH = "prompt-workbench"
    REVIEW_WORKBENCH = "review-workbench"


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
        typer.Option("--llm-config", help="LLM YAML configuration."),
    ] = cli_defaults.DEFAULT_LLM_CONFIG,
    manifest_directory: Annotated[
        Path,
        typer.Option(
            "--manifest-directory",
            help="Directory containing qualification manifests.",
        ),
    ] = cli_defaults.DEFAULT_MANIFEST_DIRECTORY,
    review_workspace: Annotated[
        Path,
        typer.Option(
            "--review-workspace",
            help="Directory containing immediate review-package subdirectories (review-workbench).",
        ),
    ] = cli_defaults.DEFAULT_PARTIAL_REVIEW_WORKSPACE,
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
        if service is ChatServiceType.REVIEW_WORKBENCH:
            review_http = ReviewWorkbenchHttpConfig(host=host, port=port)
            web_app = build_review_workbench_web_app(
                review_workspace=review_workspace,
                http_config=review_http,
            )
            authority = f"[{host}]" if ":" in host else host
            typer.echo(f"Review workbench available at http://{authority}:{port}")
            typer.echo(
                "Human decisions only; reviewer identity is self-declared. No LLM is started."
            )
            run_review_workbench_server(web_app, review_http)
            return
        http_config = PromptWorkbenchHttpConfig(host=host, port=port)
        if service is ChatServiceType.PROMPT_WORKBENCH:
            # Validate service-specific paths here: review needs neither LLM config nor manifests.
            if not llm_config.is_file():
                raise ValueError(f"LLM configuration is unavailable: {llm_config}")
            if not manifest_directory.is_dir():
                raise ValueError(f"Manifest directory is unavailable: {manifest_directory}")
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
