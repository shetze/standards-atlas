"""CLI help and shared-default regression tests."""

from typer.testing import CliRunner

from standards_atlas.application.semantic_qualification.defaults import (
    DEFAULT_EVALUATION_MAX_TOKENS,
    STATEMENT_FUNCTION_PROMPT_VERSIONS,
)
from standards_atlas.application.semantic_qualification.proposals import ProposalRunConfig
from standards_atlas.cli.main import app

runner = CliRunner()


def test_annotations_propose_help_lists_prompt_variants_and_defaults() -> None:
    result = runner.invoke(
        app,
        ["evaluation", "annotations-propose", "--help"],
        terminal_width=240,
    )

    assert result.exit_code == 0
    for prompt_version in STATEMENT_FUNCTION_PROMPT_VERSIONS:
        assert prompt_version in result.stdout
    assert str(DEFAULT_EVALUATION_MAX_TOKENS) in result.stdout


def test_proposal_config_uses_shared_max_tokens_default() -> None:
    config = ProposalRunConfig(
        corpus_id="corpus",
        task="task",
        task_version="1",
        dataset_version="1",
        prompt_version="prompt",
        provider="provider",
        model="model",
    )

    assert config.max_tokens == DEFAULT_EVALUATION_MAX_TOKENS


def test_qualification_matrix_help_exposes_mcp_lifecycle_options() -> None:
    result = runner.invoke(app, ["evaluation", "qualification-matrix", "--help"])

    assert result.exit_code == 0
    assert "--mcp-config" in result.stdout
    assert "--mcp-autostart" in result.stdout
    assert "--mcp-autostop" in result.stdout
    assert "--resume" in result.stdout
    assert "--overwrite" in result.stdout
    assert "--recompute" in result.stdout
    assert "--no-cache" in result.stdout
    assert "--no-reuse" in result.stdout
    assert "--fresh" in result.stdout
