from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.application.services.evaluation import (
    BenchmarkManifest,
    ClauseDescriptor,
    CorpusBuildConfig,
    EvaluationCorpusBuilder,
    EvaluationMatrixRunner,
    EvaluationReporter,
    EvaluationRunner,
)
from standards_atlas.domain.model import ClauseType


class FakeProvider:
    def sample_clauses(self, **kwargs):
        return (
            ClauseDescriptor(
                id="DOC:1",
                document_key="DOC",
                reference="DOC:1",
                clause_reference="1",
                clause_type=ClauseType.REQUIREMENT,
                text="The supplier shall review the plan.",
            ),
        )


class FakeGateway:
    def generate_structured(self, request):
        return StructuredGenerationResult(
            value={"summary": "Review the plan.", "confidence": 1.0},
            model=request.model or "default",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="input-hash",
            raw_response_hash="response-hash",
            duration_ms=5,
        )


def _write_resources(root: Path) -> None:
    prompt = root / "prompts" / "clause-summary" / "1.0.0"
    prompt.mkdir(parents=True)
    (prompt / "prompt.json").write_text('{"description":"test"}')
    (prompt / "system.txt").write_text("Summarize.")
    (prompt / "user.txt").write_text("{reference}: {text}")
    (prompt / "schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["summary", "confidence"],
                "properties": {
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            }
        )
    )
    corpus = root / "corpora" / "clause-summary" / "1.0.0"
    corpus.mkdir(parents=True)
    (corpus / "dataset.json").write_text(
        json.dumps(
            {
                "examples": [
                    {
                        "id": "case-1",
                        "input": {"reference": "1", "text": "Review the plan."},
                        "expected": {"summary": "Review the plan.", "confidence": 1.0},
                    }
                ]
            }
        )
    )


def test_builds_annotation_ready_corpus(tmp_path: Path) -> None:
    result = EvaluationCorpusBuilder(FakeProvider()).build(
        CorpusBuildConfig(task="clause-summary", version="local-1", count=1),
        tmp_path,
    )
    payload = json.loads(result.dataset_path.read_text())
    manifest = json.loads(result.manifest_path.read_text())
    assert payload["examples"][0]["annotation_status"] == "proposed"
    assert payload["examples"][0]["expected"] == {}
    assert manifest["sources"][0]["source_hash"]


def test_runs_complete_prompt_model_matrix_and_writes_redacted_report(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    _write_resources(resources)
    manifest = BenchmarkManifest(
        task="clause-summary",
        dataset_version="1.0.0",
        prompt_versions=("1.0.0",),
        models=("model-a", "model-b"),
        resources=resources,
        output=tmp_path / "out",
    )
    result = EvaluationMatrixRunner(EvaluationRunner(FakeGateway())).run(manifest)
    assert [run.model for run in result.runs] == ["model-a", "model-b"]
    path = EvaluationReporter().write_matrix_summary(
        result.runs,
        manifest.output / "matrix-summary.json",
        manifest_hash=result.manifest_hash,
    )
    report = json.loads(path.read_text())
    assert report["contains_case_content"] is False
    assert "output" not in report["runs"][0]["cases"][0]
    assert report["benchmark_manifest_hash"] == manifest.fingerprint()
