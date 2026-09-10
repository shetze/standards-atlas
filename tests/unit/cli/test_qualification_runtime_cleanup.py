"""Cleanup must neither retry a failed initial stop nor mask the primary error."""

import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import typer
from typer.testing import CliRunner

from standards_atlas.adapters.llm import RamaLamaServerError
from standards_atlas.cli.commands.evaluation_commands.runtime_cleanup import (
    cleanup_qualification_runtime,
)
from standards_atlas.cli.main import app


@pytest.mark.parametrize(
    "primary",
    [RuntimeError("inference"), typer.Exit(code=2), KeyboardInterrupt()],
)
def test_cleanup_preserves_active_error_and_still_releases_mcp(primary, capsys):
    server = Mock()
    server.stop.side_effect = RamaLamaServerError("still listening")
    lease = Mock(__exit__=Mock())
    cleanup_qualification_runtime(server, lease, primary_error=primary)
    lease.__exit__.assert_called_once_with(None, None, None)
    assert "RamaLama cleanup failed: still listening" in capsys.readouterr().err


def test_cleanup_only_failure_is_not_successful_exit():
    server = Mock()
    server.stop.side_effect = RamaLamaServerError("still listening")
    lease = Mock(__exit__=Mock())
    with pytest.raises(typer.Exit) as error:
        cleanup_qualification_runtime(server, lease, primary_error=None)
    assert error.value.exit_code == 2
    lease.__exit__.assert_called_once()


def test_both_cleanup_failures_are_reported_without_losing_primary(capsys):
    server = Mock()
    server.stop.side_effect = RamaLamaServerError("stop failed")
    lease = Mock(__exit__=Mock(side_effect=RuntimeError("lease failed")))
    cleanup_qualification_runtime(server, lease, primary_error=ValueError("original"))
    output = capsys.readouterr().err
    assert "stop failed" in output and "lease failed" in output


def test_initial_stop_failure_is_attempted_once_and_produces_exit_two(tmp_path, monkeypatch):
    module = importlib.import_module(
        "standards_atlas.cli.commands.evaluation_commands.qualification_matrix"
    )
    manager = Mock()
    manager.stop.side_effect = RamaLamaServerError("endpoint still serves phi-4")
    monkeypatch.setattr(module, "RamaLamaServerManager", Mock(return_value=manager))
    monkeypatch.setattr(
        module,
        "build_qualification_run_selection",
        Mock(
            return_value=(
                None,
                (SimpleNamespace(id="clause"),),
                SimpleNamespace(selected_clause_count=1, dataset_clause_count=1),
            )
        ),
    )
    monkeypatch.setattr(
        module,
        "persist_qualification_run_selection",
        Mock(
            return_value=tmp_path / "selection.json",
        ),
    )
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "qualification-matrix",
            "--manifest",
            "manifests/multidimensional-semantic-qualification-v6-applicability-presence-v1.yaml",
            "--output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2, result.output
    assert result.output.count("endpoint still serves phi-4") == 1, result.output
    manager.stop.assert_called_once()
    manager.start.assert_not_called()
    assert isinstance(result.exception, SystemExit)
