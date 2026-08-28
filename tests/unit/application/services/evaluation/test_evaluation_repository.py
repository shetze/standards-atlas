from pathlib import Path

from standards_atlas.application.services.evaluation import (
    EvaluationDatasetRepository,
    PromptRepository,
)

ROOT = Path("src/standards_atlas/resources/semantic")


def test_loads_versioned_prompt() -> None:
    prompt = PromptRepository(ROOT / "prompts").load("clause-summary", "1.0.0")
    assert prompt.task == "clause-summary"
    assert prompt.version == "1.0.0"
    assert prompt.output_schema["required"] == ["summary", "confidence"]


def test_loads_versioned_evaluation_dataset() -> None:
    dataset = EvaluationDatasetRepository(ROOT / "corpora").load("clause-summary", "1.0.0")
    assert dataset.version == "1.0.0"
    assert len(dataset.examples) == 3
    assert dataset.examples[0].tags == ("requirement", "shall")
