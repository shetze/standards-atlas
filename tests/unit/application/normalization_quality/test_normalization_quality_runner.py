import json
from pathlib import Path

from standards_atlas.application.normalization_quality import NormalizationQualityRunner
from standards_atlas.application.ports.llm_gateway import (
    StructuredGenerationResult,
)


class FakeGateway:
    def __init__(self, values):
        self.values = iter(values)
        self.requests = []

    def health(self):  # pragma: no cover - protocol completeness
        raise NotImplementedError

    def generate_structured(self, request):
        self.requests.append(request)
        value = next(self.values)
        return StructuredGenerationResult(
            value=value,
            model=request.model or "model",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="input",
            raw_response_hash="raw",
            duration_ms=12,
            cached=False,
        )


def _dataset(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "task": "semantic-profile",
                "version": "1",
                "examples": [
                    {
                        "id": "clause-1",
                        "input": {
                            "content": {"text": "The require- ments shall apply."},
                            "context": {
                                "document_key": "ISO26262-6",
                                "reference": "7.4.3",
                                "title": "Requirements",
                                "ancestor_headings": [],
                                "content_profile": "prose",
                            },
                        },
                        "expected": {"statement_function": "requirement"},
                    },
                    {
                        "id": "clause-2",
                        "input": {
                            "content": {"text": "The software unit shall be verified."},
                            "context": {
                                "document_key": "ISO26262-6",
                                "reference": "8.4.2",
                            },
                        },
                        "expected": {},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_reviews_every_corpus_item_and_ignores_semantic_expected_labels(tmp_path: Path) -> None:
    gateway = FakeGateway(
        [
            {
                "status": "suspicious",
                "findings": [
                    {
                        "type": "hyphenation_error",
                        "severity": "high",
                        "evidence": "require- ments",
                        "explanation": "Probable line-break artifact.",
                        "confidence": 0.98,
                    }
                ],
            },
            {"status": "ok", "findings": []},
        ]
    )

    run = NormalizationQualityRunner(Path("src/standards_atlas/resources/normalization")).run(
        _dataset(tmp_path / "dataset.json"),
        gateway=gateway,
        model_id="test-model",
        model_ref="test-ref",
    )

    assert run.reviewed == 2
    assert run.suspicious == 1
    assert run.failed == 0
    assert run.finding_counts() == {"hyphenation_error": 1}
    assert len(gateway.requests) == 2
    assert "statement_function" not in gateway.requests[0].user_prompt
    assert "Do not propose corrected text" in gateway.requests[0].user_prompt


def test_invalid_status_finding_combination_is_recorded_as_failure(tmp_path: Path) -> None:
    gateway = FakeGateway(
        [
            {
                "status": "ok",
                "findings": [
                    {
                        "type": "other",
                        "severity": "low",
                        "evidence": "x",
                        "explanation": "x",
                        "confidence": 0.5,
                    }
                ],
            }
        ]
    )

    run = NormalizationQualityRunner(Path("src/standards_atlas/resources/normalization")).run(
        _dataset(tmp_path / "dataset.json"),
        gateway=gateway,
        model_id="test-model",
        model_ref="test-ref",
        limit=1,
    )

    assert run.failed == 1
    assert "must not contain findings" in (run.cases[0].error or "")
