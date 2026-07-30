"""Command-line interface composition root."""

from standards_atlas.cli.apps import app

# Imports register commands on the shared Typer application tree.

# Kept as imports for focused unit tests and downstream CLI integration.

__all__ = ["app"]
