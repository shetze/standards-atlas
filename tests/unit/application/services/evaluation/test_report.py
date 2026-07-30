import json

from standards_atlas.application.evaluation.models import (
    AggregateMetrics,
    EvaluationRun,
)
from standards_atlas.application.evaluation.report import SemanticEvaluationReporter


def test_writes_model_comparison_with_ranking(tmp_path) -> None:
    metrics_a = AggregateMetrics(1, 1, 1, 1, 1, 1, 1, 1, 0.9, 0.9, 0.9, 10)
    metrics_b = AggregateMetrics(1, 1, 1, 0, 0.5, 0.5, 0.5, 1, 0.6, 0.6, 0.6, 8)
    runs = (
        EvaluationRun("task", "1", "1", "a", "fake", metrics_a, ()),
        EvaluationRun("task", "1", "1", "b", "fake", metrics_b, ()),
    )
    output = SemanticEvaluationReporter().write_comparison(runs, tmp_path / "comparison.json")
    payload = json.loads(output.read_text())
    assert payload["ranking"] == ["a", "b"]
