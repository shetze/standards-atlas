"""Command-line interface composition root."""

from standards_atlas.cli.apps import app

# Import every command module exactly once so its Typer decorators register
# commands on the shared application tree from ``standards_atlas.cli.apps``.
# Keep this list explicit: adding a command module must also update the
# composition root and the command-registration regression tests.
from standards_atlas.cli.commands import (  # noqa: F401, E402
    alignment,
    documents,
    evaluation,
    normalization,
    root,
    runtime,
    workflow,
)

__all__ = ["app"]
