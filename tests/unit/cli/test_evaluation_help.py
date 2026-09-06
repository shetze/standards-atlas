"""CLI help and shared-default regression tests."""

import yaml
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


def test_challenger_qualification_help_is_registered() -> None:
    result = runner.invoke(app, ["evaluation", "challenger-qualification", "--help"])

    assert result.exit_code == 0
    assert "--manifest" in result.stdout
    assert "--fresh" in result.stdout
    assert "--allow-reuse" in result.stdout
    assert "--challenger-source-manifest" not in result.stdout


def test_evaluation_help_lists_applicability_hard_case_analysis() -> None:
    result = runner.invoke(app, ["evaluation", "--help"])
    assert result.exit_code == 0
    assert "applicability-hard-cases" in result.stdout


def test_applicability_corpus_evaluate_help_exposes_prompt_selection() -> None:
    result = runner.invoke(app, ["evaluation", "applicability-corpus-evaluate", "--help"])

    assert result.exit_code == 0
    assert "--prompt" in result.stdout
    assert "--all-prompts" not in result.stdout


def test_applicability_corpus_migrate_help_exposes_presence_outputs() -> None:
    result = runner.invoke(app, ["evaluation", "applicability-corpus-migrate", "--help"])

    assert result.exit_code == 0
    assert "--source" in result.stdout
    assert "--output" in result.stdout
    assert "--detail-seed-output" in result.stdout


def test_applicability_corpus_migrate_writes_both_artifacts(tmp_path) -> None:
    source = tmp_path / "legacy.yaml"
    source.write_text(
        "schema_version: '2.1'\n"
        "corpus_id: applicability-hard-cases\n"
        "corpus_version: 2.1.0\n"
        "cases: []\n",
        encoding="utf-8",
    )
    output = tmp_path / "presence.yaml"
    detail_seed = tmp_path / "detail-seed.yaml"

    result = runner.invoke(
        app,
        [
            "evaluation",
            "applicability-corpus-migrate",
            "--source",
            str(source),
            "--output",
            str(output),
            "--detail-seed-output",
            str(detail_seed),
        ],
    )

    assert result.exit_code == 0
    assert yaml.safe_load(output.read_text(encoding="utf-8"))["schema_version"] == "3.0"
    assert yaml.safe_load(detail_seed.read_text(encoding="utf-8"))["schema_version"] == "1.0"


def test_applicability_detail_enrich_help_is_registered() -> None:
    result = runner.invoke(app, ["evaluation", "applicability-detail-enrich", "--help"])

    assert result.exit_code == 0
    assert "--manifest" in result.stdout
    assert "--run" in result.stdout
    assert "--consensus" in result.stdout
    assert "--selection" in result.stdout
    assert "--task-version" in result.stdout
    assert "--prompt-version" in result.stdout
    assert "--output-directory" in result.stdout
    assert "--fresh" in result.stdout


def test_applicability_end_to_end_evaluate_help_is_registered() -> None:
    result = runner.invoke(app, ["evaluation", "applicability-end-to-end-evaluate", "--help"])

    assert result.exit_code == 0
    assert "--golden" in result.stdout
    assert "--run" in result.stdout
    assert "--output" in result.stdout


def test_applicability_detail_compare_help_is_registered() -> None:
    result = runner.invoke(app, ["evaluation", "applicability-detail-compare", "--help"])

    assert result.exit_code == 0
    assert "--golden" in result.stdout
    assert "--baseline-run" in result.stdout
    assert "--candidate-directory" in result.stdout
    assert "--output" in result.stdout
