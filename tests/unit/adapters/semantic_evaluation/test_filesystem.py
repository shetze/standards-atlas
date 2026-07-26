import json
from pathlib import Path

from standards_atlas.adapters.semantic_evaluation import (
    FileSystemEvaluationReportRepository,
    FileSystemGoldenCorpusRepository,
    FileSystemPromptRepository,
)
from standards_atlas.application.semantic_evaluation import (
    EvaluationReport,
    aggregate_metrics,
)


RESOURCE_ROOT = Path("src/standards_atlas/resources/semantic")


def test_versioned_prompt_and_corpus_are_loadable():
    prompt = FileSystemPromptRepository(RESOURCE_ROOT / "prompts").load(
        "clause-summary", "1.0.0"
    )
    corpus = FileSystemGoldenCorpusRepository(RESOURCE_ROOT / "corpora").load(
        "clause-summary", "1.0.0"
    )

    assert prompt.task == "clause-summary"
    assert prompt.render(corpus.cases[0].input).startswith("Summarize this clause")
    assert len(corpus.cases) == 3


def test_report_is_written_as_stable_json(tmp_path):
    report = EvaluationReport(
        task="summary",
        prompt_id="summary",
        prompt_version="1.0.0",
        corpus_id="summary",
        corpus_version="1.0.0",
        requested_model="org/model",
        metrics=aggregate_metrics(()),
        cases=(),
        generated_at="2026-07-24T20:00:00+00:00",
    )

    path = FileSystemEvaluationReportRepository(tmp_path).save(report)

    assert path.is_file()
    assert "org-model" in str(path)
    assert json.loads(path.read_text(encoding="utf-8"))["prompt_version"] == "1.0.0"
