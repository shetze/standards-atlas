"""CLI wiring for explicit MCP recovery and read-only schema/formula diagnostics."""

import json
from unittest.mock import Mock

from typer.testing import CliRunner

from standards_atlas.adapters.mcp.compatibility import CompatibilityCheck, CompatibilityReport
from standards_atlas.adapters.mcp.process import McpServerProcessError
from standards_atlas.cli.commands import runtime
from standards_atlas.cli.main import app

runner = CliRunner()


def test_restart_uses_requested_config(tmp_path, monkeypatch) -> None:
    config = tmp_path / "mcp.yaml"
    config.write_text("mcp: {}\n")
    manager = Mock()
    factory = Mock(return_value=manager)
    monkeypatch.setattr(runtime, "managed_mcp_server", factory)

    result = runner.invoke(app, ["mcp", "restart", "--config", str(config)])

    assert result.exit_code == 0, result.output
    assert "MCP server restarted." in result.output
    factory.assert_called_once_with(config)
    manager.restart.assert_called_once_with()


def test_restart_reports_process_failure_without_success_message(tmp_path, monkeypatch) -> None:
    config = tmp_path / "mcp.yaml"
    config.write_text("mcp: {}\n")
    manager = Mock()
    manager.restart.side_effect = McpServerProcessError("endpoint is already occupied")
    monkeypatch.setattr(runtime, "managed_mcp_server", Mock(return_value=manager))

    result = runner.invoke(app, ["mcp", "restart", "--config", str(config)])

    assert result.exit_code == 2
    assert "endpoint is already occupied" in result.output
    assert "MCP server restarted." not in result.output


def test_probe_wires_repeatable_document_keys_and_retains_failure_report(
    tmp_path,
    monkeypatch,
) -> None:
    probe = Mock()
    probe.run.return_value = CompatibilityReport(
        server_name="standards-atlas",
        server_version="1.29.0",
        protocol_version="2025-11-25",
        checks=(CompatibilityCheck("engineering_document_schema", False, "server current=8"),),
    )
    factory = Mock(return_value=probe)
    monkeypatch.setattr(runtime, "McpCompatibilityProbe", factory)
    monkeypatch.setenv("TEST_MCP_TOKEN", "secret-must-not-be-in-report")
    output = tmp_path / "reports" / "probe.json"

    result = runner.invoke(
        app,
        [
            "mcp",
            "probe",
            "--url",
            "http://127.0.0.1:8765/mcp/",
            "--token-env",
            "TEST_MCP_TOKEN",
            "--document-key",
            "IEC61508-3",
            "--document-key",
            "IEC61508-2",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 1, result.output
    assert factory.call_args.kwargs["document_keys"] == ("IEC61508-3", "IEC61508-2")
    assert factory.call_args.args[0].bearer_token == "secret-must-not-be-in-report"
    assert not json.loads(output.read_text())["passed"]
    assert "secret-must-not-be-in-report" not in output.read_text()
    assert "secret-must-not-be-in-report" not in result.output
    probe.run.assert_called_once_with()


def test_probe_help_exposes_document_key() -> None:
    result = runner.invoke(app, ["mcp", "probe", "--help"])

    assert result.exit_code == 0, result.output
    assert "--document-key" in result.output


def test_codex_config_can_opt_in_to_model_only_review_tools() -> None:
    result = runner.invoke(
        app,
        [
            "mcp",
            "codex-config",
            "--url",
            "http://localhost:8765/mcp",
            "--review-preparation",
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"submit_review_selection"' in result.output
    assert '"submit_review_annotations"' in result.output
    assert "apply the fragment above" in result.output
