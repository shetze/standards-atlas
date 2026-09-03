"""Shared defaults for semantic evaluation use cases."""

from __future__ import annotations

from pathlib import Path

DEFAULT_EVALUATION_TASK = "statement-function-classification"
DEFAULT_EVALUATION_TASK_VERSION = "1.0.0"
DEFAULT_EVALUATION_DATASET_VERSION = "1.0.0"
DEFAULT_EVALUATION_PROMPT_VERSION = "structure-aware-v1"
DEFAULT_EVALUATION_MODEL = "default"
DEFAULT_EVALUATION_PROVIDER = "ramalama"
DEFAULT_EVALUATION_TEMPERATURE = 0.0
DEFAULT_EVALUATION_SEED = 0
DEFAULT_EVALUATION_MAX_TOKENS = 512
DEFAULT_EVALUATION_RETRY_ATTEMPTS = 3
DEFAULT_EVALUATION_RETRY_BACKOFF_SECONDS = 2.0
DEFAULT_EVALUATION_RETRY_TIMEOUTS = False
DEFAULT_APPLICABILITY_REVIEW_OUTPUT = Path(
    "local/review/applicability/3.0.0/applicability-golden-review.csv"
)
DEFAULT_APPLICABILITY_GOLDEN_CORPUS = Path(
    "local/review/applicability/3.0.0/applicability-golden-corpus.yaml"
)
DEFAULT_APPLICABILITY_DETAIL_SEED = Path(
    "local/review/applicability/3.0.0/applicability-detail-golden-seed.yaml"
)

STATEMENT_FUNCTION_PROMPT_VERSIONS = (
    "content-only-v1",
    "structure-aware-v1",
    "evidence-first-v1",
    "conservative-v1",
)
