"""Release qualification resources without replacing an already active error."""

from __future__ import annotations

from contextlib import AbstractContextManager

import typer

from standards_atlas.adapters.llm import RamaLamaServerManager


def cleanup_qualification_runtime(
    server: RamaLamaServerManager | None,
    mcp_lease: AbstractContextManager | None,
    *,
    primary_error: BaseException | None,
) -> None:
    """Always release both resources; cleanup-only failure still means exit 2."""
    errors: list[Exception] = []
    if server is not None:
        try:
            server.stop()
        except Exception as exc:  # Cleanup must not hide an inference failure or interruption.
            errors.append(exc)
            typer.echo(f"RamaLama cleanup failed: {exc}", err=True)
    if mcp_lease is not None:
        try:
            mcp_lease.__exit__(None, None, None)
        except Exception as exc:
            errors.append(exc)
            typer.echo(f"MCP cleanup failed: {exc}", err=True)
    if errors and primary_error is None:
        raise typer.Exit(code=2) from errors[0]
