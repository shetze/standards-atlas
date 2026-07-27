from standards_atlas.application.services.evaluation import (
    EvaluationDataset,
    EvaluationDatasetRepository,
    EvaluationExample,
    EvaluationReporter,
    EvaluationRunner,
    GoldenDataset,
    GoldenDatasetRepository,
    SemanticEvaluationReporter,
    SemanticEvaluationRunner,
)


def test_generic_evaluation_api_keeps_semantic_compatibility_aliases() -> None:
    assert GoldenDataset is EvaluationDataset
    assert GoldenDatasetRepository is EvaluationDatasetRepository
    assert SemanticEvaluationRunner is EvaluationRunner
    assert SemanticEvaluationReporter is EvaluationReporter
    assert EvaluationExample.__name__ == "EvaluationExample"
