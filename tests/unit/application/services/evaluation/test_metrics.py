import pytest

from standards_atlas.application.services.evaluation.metrics import calculate_metrics


def test_exact_output_has_perfect_metrics_and_confidence() -> None:
    output = {"labels": ["requirement", "safety"], "confidence": 0.9}
    metrics = calculate_metrics(output, output)
    assert metrics.exact_match
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1 == 1.0
    assert metrics.confidence == 0.9


def test_partial_multilabel_output_calculates_precision_and_recall() -> None:
    actual = {"labels": ["requirement", "note"]}
    expected = {"labels": ["requirement", "safety"]}
    metrics = calculate_metrics(actual, expected)
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.recall == pytest.approx(0.5)
    assert metrics.f1 == pytest.approx(0.5)
