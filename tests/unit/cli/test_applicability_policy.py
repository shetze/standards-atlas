from typer.testing import CliRunner

from standards_atlas.cli.main import app

runner = CliRunner()


def test_evaluation_help_lists_applicability_policy_commands() -> None:
    result = runner.invoke(app, ["evaluation", "--help"])

    assert result.exit_code == 0
    assert "applicability-policy-replay" in result.stdout
    assert "applicability-policy-evaluate" in result.stdout
