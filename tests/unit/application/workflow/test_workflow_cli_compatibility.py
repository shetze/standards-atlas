from pathlib import Path

import click
from typer.main import get_command

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.application.workflow import EndToEndWorkflowService
from standards_atlas.cli.main import app

_COMMAND_DEPTHS = {
    ("docling", "convert"): 2,
    ("atlasdata", "onboard-docling"): 2,
    ("atlasdata", "onboard-docling-parts"): 2,
    ("document", "import"): 2,
    ("normalize", "run"): 2,
    ("references", "detect"): 2,
    ("align", "run"): 2,
    ("align", "review-export"): 2,
    ("document", "enrich-content"): 2,
    ("document", "classify-taxonomy"): 2,
    ("document", "enrich-context"): 2,
    ("document", "export", "markdown"): 3,
    ("document", "export", "doorstop"): 3,
    ("document", "derive-part"): 2,
}


def _click_command(path: tuple[str, ...]) -> click.Command:
    command: click.Command = get_command(app)
    for name in path:
        assert hasattr(command, "commands")
        command = command.commands[name]
    return command


def _command_path(command: tuple[str, ...]) -> tuple[str, ...]:
    cli_tokens = command[3:]
    for path, depth in _COMMAND_DEPTHS.items():
        if cli_tokens[:depth] == path:
            return path
    raise AssertionError(f"Unknown workflow CLI command: {' '.join(command)}")


def test_workflow_options_exist_on_the_real_cli() -> None:
    from typer.testing import CliRunner

    catalog = YamlStandardCatalogReader().read(Path("manifests/standards.yaml"))
    service = EndToEndWorkflowService()
    runner = CliRunner()
    help_by_path: dict[tuple[str, ...], str] = {}

    for force in (False, True):
        plan = service.plan(
            catalog,
            family_keys=("EN50716", "IEC29100", "ISO26262"),
            catalog_root=Path.cwd(),
            force=force,
        )
        for step in plan.steps:
            path = _command_path(step.command)
            if path not in help_by_path:
                result = runner.invoke(app, [*path, "--help"])
                assert result.exit_code == 0, result.output
                help_by_path[path] = result.output
            generated_options = {
                token for token in step.command[3 + len(path) :] if token.startswith("-")
            }
            for option in generated_options:
                assert option in help_by_path[path], (
                    f"Unsupported option for {' '.join(path)}: {option}"
                )
