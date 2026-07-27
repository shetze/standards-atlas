"""Task-neutral metrics for structured semantic outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from standards_atlas.application.semantic_evaluation.models import ExampleMetrics


def calculate_metrics(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> ExampleMetrics:
    actual_items = _flatten(actual)
    expected_items = _flatten(expected)
    true_positives = len(actual_items & expected_items)
    precision = true_positives / len(actual_items) if actual_items else float(not expected_items)
    recall = true_positives / len(expected_items) if expected_items else float(not actual_items)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    confidence = _confidence(actual)
    return ExampleMetrics(
        exact_match=actual == expected,
        precision=precision,
        recall=recall,
        f1=f1,
        confidence=confidence,
    )


def empty_metrics() -> ExampleMetrics:
    return ExampleMetrics(False, 0.0, 0.0, 0.0, None)


def _flatten(value: Any, prefix: str = "") -> set[tuple[str, str]]:
    items: set[tuple[str, str]] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "confidence":
                continue
            path = f"{prefix}.{key}" if prefix else str(key)
            items.update(_flatten(child, path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            items.add((prefix, _canonical(child)))
    else:
        items.add((prefix, _canonical(value)))
    return items


def _canonical(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _confidence(value: Mapping[str, Any]) -> float | None:
    confidence = value.get("confidence")
    if isinstance(confidence, int | float) and 0.0 <= float(confidence) <= 1.0:
        return float(confidence)
    return None
