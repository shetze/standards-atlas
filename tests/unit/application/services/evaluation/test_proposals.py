from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.application.ports.llm_gateway import (
    LlmHealth,
    StructuredGenerationResult,
)
from standards_atlas.application.services.evaluation.defaults import (
    DEFAULT_EVALUATION_MAX_TOKENS,
)
from standards_atlas.application.services.evaluation.proposals import (
    BaselineProposalGenerator,
    ProposalRunConfig,
)


class MissingPrimaryRoleGateway:
    def health(self):
        return LlmHealth(True, ("test-model",))

    def generate_structured(self, request):
        return StructuredGenerationResult(
            value={
                "statement_functions": ["description"],
                "primary_function": "requirement",
                "confidence": 0.8,
                "rationale": "The clause defines a normative requirement.",
            },
            model=request.model or "test-model",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="input-hash",
            raw_response_hash="response-hash",
            duration_ms=12,
            raw_response={"choices": []},
        )


class FakeGateway:
    def health(self):
        return LlmHealth(True, ("test-model",))

    def generate_structured(self, request):
        return StructuredGenerationResult(
            value={
                "statement_functions": ["requirement"],
                "primary_function": "requirement",
                "confidence": 0.9,
                "rationale": "The clause uses normative language.",
            },
            model=request.model or "test-model",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="input-hash",
            raw_response_hash="response-hash",
            duration_ms=12,
            raw_response={"choices": []},
        )


def test_proposal_generation_persists_request_response_and_resumes(tmp_path: Path):
    corpus_root = tmp_path / "corpora"
    dataset_dir = corpus_root / "statement-function-classification" / "1.0.0"
    dataset_dir.mkdir(parents=True)
    dataset = {
        "task": "statement-function-classification",
        "version": "1.0.0",
        "examples": [
            {
                "id": "clause-1",
                "input": {
                    "content": {
                        "hash": "sha256:" + "a" * 64,
                        "text": "The supplier shall verify the result.",
                    },
                    "context": {
                        "knowledge_domain": "functional-safety",
                        "document_key": "IEC61508-3",
                        "clause_id": "clause-1",
                        "reference": "7.4.2",
                        "title": "Verification",
                        "parent_id": None,
                        "structural_roles": ["requirement"],
                    },
                },
                "expected": {},
            }
        ],
    }
    (dataset_dir / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
    resources = Path("src/standards_atlas/resources/semantic")
    config = ProposalRunConfig(
        corpus_id="semantic-roles-v1",
        task="statement-function-classification",
        task_version="1.0.0",
        dataset_version="1.0.0",
        prompt_version="structure-aware-v1",
        provider="fake",
        model="test-model",
    )
    generator = BaselineProposalGenerator(FakeGateway())
    result = generator.run(
        config,
        resources=resources,
        corpus_root=corpus_root,
        output_root=tmp_path / "evaluation",
    )
    assert result.generated == 1
    assert result.failed == 0
    case = result.run_directory / "clause-1"
    assert (case / "request.json").exists()
    assert (case / "response.json").exists()
    assert (case / "evaluation.yaml").exists()
    resumed = generator.run(
        config,
        resources=resources,
        corpus_root=corpus_root,
        output_root=tmp_path / "evaluation",
    )
    assert resumed.skipped == 1


def test_limit_applies_to_pending_examples_after_existing_annotations(tmp_path: Path):
    corpus_root = tmp_path / "corpora"
    dataset_dir = corpus_root / "statement-function-classification" / "1.0.0"
    dataset_dir.mkdir(parents=True)
    examples = []
    for index in range(3):
        examples.append(
            {
                "id": f"clause-{index}",
                "input": {
                    "content": {
                        "hash": "sha256:" + str(index + 1) * 64,
                        "text": f"Clause {index} shall be evaluated.",
                    },
                    "context": {
                        "knowledge_domain": "functional-safety",
                        "document_key": "IEC61508-3",
                        "clause_id": f"clause-{index}",
                        "reference": str(index),
                        "title": None,
                        "parent_id": None,
                        "structural_roles": [],
                    },
                },
                "expected": {},
            }
        )
    dataset = {
        "task": "statement-function-classification",
        "version": "1.0.0",
        "examples": examples,
    }
    (dataset_dir / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
    resources = Path("src/standards_atlas/resources/semantic")
    output_root = tmp_path / "evaluation"
    generator = BaselineProposalGenerator(FakeGateway())
    base = ProposalRunConfig(
        corpus_id="semantic-roles-v1",
        task="statement-function-classification",
        task_version="1.0.0",
        dataset_version="1.0.0",
        prompt_version="structure-aware-v1",
        provider="fake",
        model="test-model",
        limit=1,
    )
    first = generator.run(
        base,
        resources=resources,
        corpus_root=corpus_root,
        output_root=output_root,
    )
    second = generator.run(
        base,
        resources=resources,
        corpus_root=corpus_root,
        output_root=output_root,
    )
    assert first.generated == 1
    assert second.generated == 1
    assert second.skipped == 1


def test_proposal_generation_reports_progress(tmp_path: Path):
    corpus_root = tmp_path / "corpora"
    dataset_dir = corpus_root / "statement-function-classification" / "1.0.0"
    dataset_dir.mkdir(parents=True)
    dataset = {
        "task": "statement-function-classification",
        "version": "1.0.0",
        "examples": [
            {
                "id": "clause-1",
                "input": {
                    "content": {
                        "hash": "sha256:" + "a" * 64,
                        "text": "The supplier shall verify the result.",
                    },
                    "context": {
                        "knowledge_domain": "functional-safety",
                        "document_key": "IEC61508-3",
                        "clause_id": "clause-1",
                        "reference": "7.4.2",
                        "title": "Verification",
                        "parent_id": None,
                        "structural_roles": ["requirement"],
                    },
                },
                "expected": {},
            }
        ],
    }
    (dataset_dir / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
    progress = []
    result = BaselineProposalGenerator(FakeGateway()).run(
        ProposalRunConfig(
            corpus_id="semantic-roles-v1",
            task="statement-function-classification",
            task_version="1.0.0",
            dataset_version="1.0.0",
            prompt_version="structure-aware-v1",
            provider="fake",
            model="test-model",
        ),
        resources=Path("src/standards_atlas/resources/semantic"),
        corpus_root=corpus_root,
        output_root=tmp_path / "evaluation",
        progress=progress.append,
    )
    assert result.generated == 1
    assert len(progress) == 2
    assert [item.status for item in progress] == ["processing", "generated"]
    assert all(item.current == 1 for item in progress)
    assert all(item.total == 1 for item in progress)
    assert all(item.document_key == "IEC61508-3" for item in progress)
    assert all(item.reference == "7.4.2" for item in progress)
    assert all(item.title == "Verification" for item in progress)


def test_proposals_are_isolated_by_provider_and_model(tmp_path: Path):
    corpus_root = tmp_path / "corpora"
    dataset_dir = corpus_root / "statement-function-classification" / "1.0.0"
    dataset_dir.mkdir(parents=True)
    dataset = {
        "task": "statement-function-classification",
        "version": "1.0.0",
        "examples": [
            {
                "id": "clause-1",
                "input": {
                    "content": {"hash": "sha256:" + "a" * 64, "text": "The supplier shall verify."},
                    "context": {
                        "knowledge_domain": "functional-safety",
                        "document_key": "IEC61508-3",
                        "clause_id": "clause-1",
                        "reference": "7.4.2",
                        "title": "Verification",
                        "parent_id": None,
                        "structural_roles": [],
                    },
                },
                "expected": {},
            }
        ],
    }
    (dataset_dir / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
    generator = BaselineProposalGenerator(FakeGateway())
    common = dict(
        corpus_id="semantic-roles-v1",
        task="statement-function-classification",
        task_version="1.0.0",
        dataset_version="1.0.0",
        prompt_version="structure-aware-v1",
    )
    first = generator.run(
        ProposalRunConfig(**common, provider="ramalama", model="granite"),
        resources=Path("src/standards_atlas/resources/semantic"),
        corpus_root=corpus_root,
        output_root=tmp_path / "evaluation",
    )
    second = generator.run(
        ProposalRunConfig(**common, provider="codex", model="luna"),
        resources=Path("src/standards_atlas/resources/semantic"),
        corpus_root=corpus_root,
        output_root=tmp_path / "evaluation",
    )
    assert first.generated == 1
    assert second.generated == 1
    assert first.run_directory != second.run_directory
    assert (first.run_directory / "clause-1" / "evaluation.yaml").exists()
    assert (second.run_directory / "clause-1" / "evaluation.yaml").exists()


class DuplicateRoleGateway(FakeGateway):
    def generate_structured(self, request):
        result = super().generate_structured(request)
        return result.__class__(
            **{
                **vars(result),
                "value": {
                    "statement_functions": ["requirement", "requirement"],
                    "primary_function": "requirement",
                    "confidence": 0.9,
                    "rationale": "Normative requirement.",
                },
            }
        )


class TransientGateway(FakeGateway):
    def __init__(self):
        self.calls = 0

    def generate_structured(self, request):
        from standards_atlas.adapters.llm import LlmUnavailableError

        self.calls += 1
        if self.calls < 3:
            raise LlmUnavailableError("timed out")
        return super().generate_structured(request)


def _single_example_corpus(tmp_path: Path) -> Path:
    corpus_root = tmp_path / "corpora"
    dataset_dir = corpus_root / "statement-function-classification" / "1.0.0"
    dataset_dir.mkdir(parents=True)
    dataset = {
        "task": "statement-function-classification",
        "version": "1.0.0",
        "examples": [
            {
                "id": "clause-1",
                "input": {
                    "content": {"hash": "sha256:" + "a" * 64, "text": "The supplier shall verify."},
                    "context": {
                        "knowledge_domain": "functional-safety",
                        "document_key": "IEC61508-3",
                        "clause_id": "clause-1",
                        "reference": "7.4.2",
                        "title": "Verification",
                        "parent_id": None,
                        "structural_roles": [],
                    },
                },
                "expected": {},
            }
        ],
    }
    (dataset_dir / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
    return corpus_root


def test_duplicate_statement_functions_are_normalized(tmp_path: Path):
    result = BaselineProposalGenerator(DuplicateRoleGateway()).run(
        ProposalRunConfig(
            corpus_id="semantic-roles-v1",
            task="statement-function-classification",
            task_version="1.0.0",
            dataset_version="1.0.0",
            prompt_version="structure-aware-v1",
            provider="fake",
            model="duplicate-model",
        ),
        resources=Path("src/standards_atlas/resources/semantic"),
        corpus_root=_single_example_corpus(tmp_path),
        output_root=tmp_path / "evaluation",
    )
    assert result.generated == 1
    assert result.failed == 0


def test_transient_endpoint_failures_are_retried(tmp_path: Path):
    gateway = TransientGateway()
    result = BaselineProposalGenerator(gateway).run(
        ProposalRunConfig(
            corpus_id="semantic-roles-v1",
            task="statement-function-classification",
            task_version="1.0.0",
            dataset_version="1.0.0",
            prompt_version="structure-aware-v1",
            provider="fake",
            model="retry-model",
            retry_attempts=3,
            retry_backoff_seconds=0,
        ),
        resources=Path("src/standards_atlas/resources/semantic"),
        corpus_root=_single_example_corpus(tmp_path),
        output_root=tmp_path / "evaluation",
    )
    assert gateway.calls == 3
    assert result.generated == 1
    assert result.failed == 0


def test_progress_identifies_clause_and_reports_failure_detail(tmp_path: Path):
    class FailingGateway(FakeGateway):
        def generate_structured(self, request):
            from standards_atlas.application.ports.llm_gateway import LlmUnavailableError

            raise LlmUnavailableError("timed out")

    progress = []
    result = BaselineProposalGenerator(FailingGateway()).run(
        ProposalRunConfig(
            corpus_id="semantic-roles-v1",
            task="statement-function-classification",
            task_version="1.0.0",
            dataset_version="1.0.0",
            prompt_version="structure-aware-v1",
            provider="fake",
            model="timeout-model",
            retry_attempts=2,
            retry_backoff_seconds=0,
        ),
        resources=Path("src/standards_atlas/resources/semantic"),
        corpus_root=_single_example_corpus(tmp_path),
        output_root=tmp_path / "evaluation",
        progress=progress.append,
    )

    assert result.failed == 1
    assert [item.status for item in progress] == ["processing", "retrying", "failed"]
    assert all(item.document_key == "IEC61508-3" for item in progress)
    assert all(item.reference == "7.4.2" for item in progress)
    assert all(item.title == "Verification" for item in progress)
    assert progress[1].attempt == 1
    assert progress[1].max_attempts == 2
    assert progress[1].detail == "LlmUnavailableError: timed out"
    assert progress[-1].detail == "LlmUnavailableError: timed out"


def test_timeout_is_not_retried_by_default_and_writes_failure_diagnostics(tmp_path: Path):
    class TimeoutGateway(FakeGateway):
        def __init__(self):
            self.calls = 0

        def generate_structured(self, request):
            from standards_atlas.application.ports.llm_gateway import LlmTimeoutError

            self.calls += 1
            raise LlmTimeoutError("LLM request timed out after 120s")

    gateway = TimeoutGateway()
    result = BaselineProposalGenerator(gateway).run(
        ProposalRunConfig(
            corpus_id="semantic-roles-v1",
            task="statement-function-classification",
            task_version="1.0.0",
            dataset_version="1.0.0",
            prompt_version="structure-aware-v1",
            provider="fake",
            model="timeout-model",
            retry_attempts=3,
            retry_backoff_seconds=0,
        ),
        resources=Path("src/standards_atlas/resources/semantic"),
        corpus_root=_single_example_corpus(tmp_path),
        output_root=tmp_path / "evaluation",
    )

    assert gateway.calls == 1
    assert result.failed == 1
    failure = json.loads(
        (result.run_directory / "clause-1" / "failure.json").read_text(encoding="utf-8")
    )
    assert failure["error"]["category"] == "generation_timeout"
    assert failure["request"]["max_tokens"] == DEFAULT_EVALUATION_MAX_TOKENS
    assert failure["request"]["request_hash"].startswith("sha256:")


def test_timeout_can_be_retried_explicitly(tmp_path: Path):
    class TimeoutThenSuccessGateway(FakeGateway):
        def __init__(self):
            self.calls = 0

        def generate_structured(self, request):
            from standards_atlas.application.ports.llm_gateway import LlmTimeoutError

            self.calls += 1
            if self.calls == 1:
                raise LlmTimeoutError("timed out")
            return super().generate_structured(request)

    gateway = TimeoutThenSuccessGateway()
    result = BaselineProposalGenerator(gateway).run(
        ProposalRunConfig(
            corpus_id="semantic-roles-v1",
            task="statement-function-classification",
            task_version="1.0.0",
            dataset_version="1.0.0",
            prompt_version="structure-aware-v1",
            provider="fake",
            model="retry-timeout-model",
            retry_attempts=2,
            retry_backoff_seconds=0,
            retry_timeouts=True,
        ),
        resources=Path("src/standards_atlas/resources/semantic"),
        corpus_root=_single_example_corpus(tmp_path),
        output_root=tmp_path / "evaluation",
    )

    assert gateway.calls == 2
    assert result.generated == 1


def test_missing_primary_function_is_added_to_statement_functions(tmp_path: Path):
    result = BaselineProposalGenerator(MissingPrimaryRoleGateway()).run(
        ProposalRunConfig(
            corpus_id="semantic-roles-v1",
            task="statement-function-classification",
            task_version="1.0.0",
            dataset_version="1.0.0",
            prompt_version="structure-aware-v1",
            provider="fake",
            model="inconsistent-model",
        ),
        resources=Path("src/standards_atlas/resources/semantic"),
        corpus_root=_single_example_corpus(tmp_path),
        output_root=tmp_path / "evaluation",
    )

    assert result.generated == 1
    assert result.failed == 0
    evaluation = (result.run_directory / "clause-1" / "evaluation.yaml").read_text(encoding="utf-8")
    assert "- requirement" in evaluation
    assert "primary_function: requirement" in evaluation
