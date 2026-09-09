"""In-process invocation of existing command/application boundaries for composed tasks."""

from __future__ import annotations

from contextlib import chdir
from pathlib import Path

import typer
from typer.main import get_command


class InProcessWorkflowCommandRunner:
    """Execute a serial workflow through the registered CLI, without shell/subprocess glue.

    Parsing/defaults and service composition stay owned by the focused commands.
    This runner is sequential: changing the working directory is process-local.
    """

    def run(self, command: tuple[str, ...], cwd: Path) -> None:
        if command[:3] != ("uv", "run", "standards-atlas") or len(command) < 5:
            raise ValueError("in-process workflow requires a registered Standards Atlas command")
        # Lazy import avoids the CLI registration/composition cycle.
        from standards_atlas.cli import app

        with chdir(cwd):
            result = get_command(app).main(args=list(command[3:]), standalone_mode=False)
        # Click returns explicit Exit codes in non-standalone mode; a nonzero
        # command must not be checkpointed as a successfully completed stage.
        if isinstance(result, int) and result:
            raise typer.Exit(code=result)
