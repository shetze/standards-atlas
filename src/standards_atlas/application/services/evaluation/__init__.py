"""Reusable prompt, model, dataset, regression, and reporting evaluation services."""

from standards_atlas.application.services.evaluation.clause_access import (
    ClauseDescriptor,
    ClauseFilter,
    ClauseProvider,
    DocumentDescriptor,
    SamplingStrategy,
)
from standards_atlas.application.services.evaluation.models import (
    AggregateMetrics,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationExample,
    EvaluationRun,
    ExampleMetrics,
    GoldenDataset,
    GoldenExample,
    PromptDefinition,
    RegressionResult,
)
from standards_atlas.application.services.evaluation.report import (
    EvaluationReporter,
    SemanticEvaluationReporter,
)
from standards_atlas.application.services.evaluation.repository import (
    EvaluationDatasetRepository,
    GoldenDatasetRepository,
    PromptRepository,
)
from standards_atlas.application.services.evaluation.runner import (
    EvaluationRunner,
    SemanticEvaluationRunner,
    compare_runs,
)
from standards_atlas.application.services.evaluation.workflow import (
    BenchmarkManifest,
    BenchmarkMatrixResult,
    CorpusBuildConfig,
    CorpusBuildResult,
    EvaluationCorpusBuilder,
    EvaluationMatrixRunner,
)

__all__ = [
    "AggregateMetrics",
    "EvaluationCaseResult",
    "EvaluationDataset",
    "EvaluationDatasetRepository",
    "EvaluationExample",
    "EvaluationReporter",
    "EvaluationRun",
    "EvaluationRunner",
    "ExampleMetrics",
    "GoldenDataset",
    "GoldenDatasetRepository",
    "GoldenExample",
    "PromptDefinition",
    "PromptRepository",
    "RegressionResult",
    "SemanticEvaluationReporter",
    "SemanticEvaluationRunner",
    "compare_runs",
    "ClauseDescriptor",
    "ClauseFilter",
    "ClauseProvider",
    "DocumentDescriptor",
    "SamplingStrategy",
    "BenchmarkManifest",
    "BenchmarkMatrixResult",
    "CorpusBuildConfig",
    "CorpusBuildResult",
    "EvaluationCorpusBuilder",
    "EvaluationMatrixRunner",
]
