"""Single source of truth for command-line defaults."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.application.semantic_qualification import defaults as evaluation_defaults
from standards_atlas.application.semantic_qualification.clause_access import SamplingStrategy

# Re-export application-level evaluation defaults for CLI declarations. Keeping
# these aliases explicit makes the public CLI-default surface easy to inspect and
# prevents Typer declarations from defining a second, divergent set of values.
DEFAULT_EVALUATION_TASK = evaluation_defaults.DEFAULT_EVALUATION_TASK
DEFAULT_EVALUATION_TASK_VERSION = evaluation_defaults.DEFAULT_EVALUATION_TASK_VERSION
DEFAULT_EVALUATION_DATASET_VERSION = evaluation_defaults.DEFAULT_EVALUATION_DATASET_VERSION
DEFAULT_EVALUATION_PROMPT_VERSION = evaluation_defaults.DEFAULT_EVALUATION_PROMPT_VERSION
DEFAULT_EVALUATION_MODEL = evaluation_defaults.DEFAULT_EVALUATION_MODEL
DEFAULT_EVALUATION_PROVIDER = evaluation_defaults.DEFAULT_EVALUATION_PROVIDER
DEFAULT_EVALUATION_TEMPERATURE = evaluation_defaults.DEFAULT_EVALUATION_TEMPERATURE
DEFAULT_EVALUATION_SEED = evaluation_defaults.DEFAULT_EVALUATION_SEED
DEFAULT_EVALUATION_MAX_TOKENS = evaluation_defaults.DEFAULT_EVALUATION_MAX_TOKENS
DEFAULT_EVALUATION_RETRY_ATTEMPTS = evaluation_defaults.DEFAULT_EVALUATION_RETRY_ATTEMPTS
DEFAULT_EVALUATION_RETRY_BACKOFF_SECONDS = (
    evaluation_defaults.DEFAULT_EVALUATION_RETRY_BACKOFF_SECONDS
)
DEFAULT_EVALUATION_RETRY_TIMEOUTS = evaluation_defaults.DEFAULT_EVALUATION_RETRY_TIMEOUTS

DEFAULT_LLM_CONFIG = Path("cfg/llm.yaml")
DEFAULT_STANDARDS_MANIFEST = Path("manifests/standards.yaml")
DEFAULT_QUALIFICATION_MATRIX = Path(
    "manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml"
)
DEFAULT_MCP_CONFIG = Path("cfg/mcp.yaml")
DEFAULT_MCP_TOKEN_ENVIRONMENT_VARIABLE = "STANDARDS_ATLAS_MCP_TOKEN"
DEFAULT_MCP_TIMEOUT_SECONDS = 10.0
DEFAULT_MCP_SERVER_NAME = "standards-atlas"
DEFAULT_CHAT_HOST = "127.0.0.1"
DEFAULT_CHAT_PORT = 8765
DEFAULT_MANIFEST_DIRECTORY = Path("manifests")

DEFAULT_ATLAS_ROOT = Path(".atlas")
DEFAULT_WORKSPACE = Path(".atlas/data")
DEFAULT_CACHE_ROOT = Path(".atlas/cache")
DEFAULT_WORK_ROOT = Path(".atlas/work")
DEFAULT_LOCAL_ROOT = Path("local")
DEFAULT_REVIEW_ROOT = Path("local/review")
DEFAULT_APPLICABILITY_REVIEW_OUTPUT = evaluation_defaults.DEFAULT_APPLICABILITY_REVIEW_OUTPUT
DEFAULT_APPLICABILITY_GOLDEN_CORPUS = evaluation_defaults.DEFAULT_APPLICABILITY_GOLDEN_CORPUS
DEFAULT_APPLICABILITY_DETAIL_SEED = evaluation_defaults.DEFAULT_APPLICABILITY_DETAIL_SEED
DEFAULT_EVALUATION_CORPUS_ROOT = Path(".atlas/data/evaluation/corpora")
DEFAULT_EVALUATION_OUTPUT = Path(".atlas/data/evaluation")
DEFAULT_EVALUATION_RESOURCES = Path("src/standards_atlas/resources/semantic")
DEFAULT_SEMANTIC_EVALUATION_OUTPUT = Path(".atlas/data/semantic/evaluations")
DEFAULT_GOLDEN_CORPUS = Path("tests/golden_corpus")

DEFAULT_CORPUS_STRATEGY = SamplingStrategy.BALANCED_BY_DOCUMENT
DEFAULT_CORPUS_INCLUDE_TEXT = True
DEFAULT_KNOWLEDGE_DOMAIN = "default"

DEFAULT_ATLASDATA_DIGITS = 8
DEFAULT_DOORSTOP_SEPARATOR = "-"
DEFAULT_DOORSTOP_TEMPLATE = "atlas-clean"
DEFAULT_MARKDOWN_REPLACE = True
DEFAULT_DOORSTOP_VALIDATE = True
DEFAULT_DOORSTOP_REPLACE = True
DEFAULT_DOORSTOP_INITIALIZE_GIT = True
DEFAULT_PUBLISH_REPLACE = True

DEFAULT_ALIGNMENT_CONTEXT_BEFORE = 2
DEFAULT_ALIGNMENT_CONTEXT_AFTER = 4

DEFAULT_FALSE = False
DEFAULT_TRUE = True
DEFAULT_NONE = None
