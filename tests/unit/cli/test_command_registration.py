"""Regression tests for deterministic CLI command registration."""

from typer.testing import CliRunner

from standards_atlas.cli.main import app

runner = CliRunner()


def test_composition_root_registers_docling_convert() -> None:
    result = runner.invoke(app, ["docling", "convert", "--help"])

    assert result.exit_code == 0, result.output


def test_composition_root_registers_document_doorstop_export() -> None:
    result = runner.invoke(app, ["document", "export", "doorstop", "--help"])

    assert result.exit_code == 0, result.output
