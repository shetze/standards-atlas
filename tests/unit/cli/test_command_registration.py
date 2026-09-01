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


def test_composition_root_registers_atlasdata_onboard_family() -> None:
    result = runner.invoke(app, ["atlasdata", "onboard-family", "--help"])

    assert result.exit_code == 0, result.output


def test_composition_root_registers_context_subject_vocabulary() -> None:
    result = runner.invoke(app, ["context", "subject-vocabulary", "--help"])

    assert result.exit_code == 0, result.output


def test_composition_root_registers_complytime_feedback_import() -> None:
    result = runner.invoke(app, ["evaluation", "complytime-feedback", "--help"])

    assert result.exit_code == 0, result.output


def test_composition_root_registers_governance_profile_validate() -> None:
    result = runner.invoke(app, ["governance", "profile", "validate", "--help"])

    assert result.exit_code == 0, result.output
