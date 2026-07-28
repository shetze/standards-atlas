from standards_atlas.application.services.evaluation import defaults as evaluation_defaults
from standards_atlas.cli import defaults as cli_defaults


def test_cli_reexports_all_evaluation_defaults() -> None:
    assert cli_defaults.DEFAULT_EVALUATION_TASK == evaluation_defaults.DEFAULT_EVALUATION_TASK
    assert (
        cli_defaults.DEFAULT_EVALUATION_TASK_VERSION
        == evaluation_defaults.DEFAULT_EVALUATION_TASK_VERSION
    )
    assert (
        cli_defaults.DEFAULT_EVALUATION_DATASET_VERSION
        == evaluation_defaults.DEFAULT_EVALUATION_DATASET_VERSION
    )
    assert (
        cli_defaults.DEFAULT_EVALUATION_PROMPT_VERSION
        == evaluation_defaults.DEFAULT_EVALUATION_PROMPT_VERSION
    )
    assert cli_defaults.DEFAULT_EVALUATION_MODEL == evaluation_defaults.DEFAULT_EVALUATION_MODEL
    assert (
        cli_defaults.DEFAULT_EVALUATION_PROVIDER == evaluation_defaults.DEFAULT_EVALUATION_PROVIDER
    )
    assert (
        cli_defaults.DEFAULT_EVALUATION_TEMPERATURE
        == evaluation_defaults.DEFAULT_EVALUATION_TEMPERATURE
    )
    assert cli_defaults.DEFAULT_EVALUATION_SEED == evaluation_defaults.DEFAULT_EVALUATION_SEED
    assert (
        cli_defaults.DEFAULT_EVALUATION_MAX_TOKENS
        == evaluation_defaults.DEFAULT_EVALUATION_MAX_TOKENS
    )
    assert (
        cli_defaults.DEFAULT_EVALUATION_RETRY_ATTEMPTS
        == evaluation_defaults.DEFAULT_EVALUATION_RETRY_ATTEMPTS
    )
    assert (
        cli_defaults.DEFAULT_EVALUATION_RETRY_BACKOFF_SECONDS
        == evaluation_defaults.DEFAULT_EVALUATION_RETRY_BACKOFF_SECONDS
    )
    assert (
        cli_defaults.DEFAULT_EVALUATION_RETRY_TIMEOUTS
        == evaluation_defaults.DEFAULT_EVALUATION_RETRY_TIMEOUTS
    )
