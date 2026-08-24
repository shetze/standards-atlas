"""Baseline proposal generation with durable requests and provider responses."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.evaluation.repository import (
    EvaluationDatasetRepository,
    PromptRepository,
)
from standards_atlas.application.evaluation.schema import validate_schema
from standards_atlas.application.ontology import (
    OntologyReference,
    ResourceOntologyDefinitionRepository,
)
from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
    StructuredGenerationRequest,
)
from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.adaptive_interview import (
    AdaptiveInterviewPlanner,
    InterviewDimension,
    focused_response_schema,
    follow_up_question,
)
from standards_atlas.application.semantic_qualification.annotations import (
    AnnotationGenerator,
    AnnotationLifecycleStatus,
    ClauseEvaluationAnnotation,
    StatementFunctionSelection,
)
from standards_atlas.application.semantic_qualification.batch import (
    ProposalBatchExecutor,
    ProposalItemOutcome,
)
from standards_atlas.application.semantic_qualification.defaults import (
    DEFAULT_EVALUATION_MAX_TOKENS,
    DEFAULT_EVALUATION_RETRY_ATTEMPTS,
    DEFAULT_EVALUATION_RETRY_BACKOFF_SECONDS,
    DEFAULT_EVALUATION_RETRY_TIMEOUTS,
    DEFAULT_EVALUATION_SEED,
    DEFAULT_EVALUATION_TEMPERATURE,
)
from standards_atlas.application.semantic_qualification.eligibility import (
    SemanticTaskEligibilityPolicy,
    eligibility_from_input,
)
from standards_atlas.application.semantic_qualification.progress import (
    ProposalProgress,
    ProposalProgressReporter,
)
from standards_atlas.application.semantic_qualification.request_builder import (
    build_clause_reference,
    build_proposal_request,
    serialize_generation_request,
)
from standards_atlas.application.semantic_qualification.retry import generate_with_retry


class SemanticTaskDefinition(BaseModel):
    """Versioned semantic task contract."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    task: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = ""
    canonical_task: str | None = None
    aliases: tuple[str, ...] = ()
    ontologies: dict[str, OntologyReference] = Field(default_factory=dict)
    taxonomy: tuple[str, ...] = ()
    knowledge_taxonomy: tuple[str, ...] = ()
    process_taxonomy: tuple[str, ...] = ()
    applicability_taxonomy: tuple[str, ...] = ()
    role_relation_taxonomy: tuple[str, ...] = ()
    multi_label: bool = True
    allow_unclassified: bool = True
    supported_item_kinds: tuple[str, ...] = ("clause",)
    excluded_content_profiles: tuple[str, ...] = ()
    alternative_tasks: dict[str, str] = Field(default_factory=dict)


class SemanticTaskRepository:
    """Load task metadata plus independently versioned ontology dimensions."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._ontology_repository = ResourceOntologyDefinitionRepository()

    def load(self, task: str, version: str) -> tuple[SemanticTaskDefinition, dict[str, Any]]:
        root = self._root / task / version
        metadata = yaml.safe_load((root / "task.yaml").read_text(encoding="utf-8")) or {}
        require_supported_schema("semantic-task-resource", metadata.get("schema_version"))
        references = {
            dimension: OntologyReference.model_validate(reference)
            for dimension, reference in dict(metadata.get("ontologies", {})).items()
        }
        loaded = {
            dimension: self._ontology_repository.load(reference.id, reference.version)
            for dimension, reference in references.items()
        }
        expected_dimensions = {
            dimension: taxonomy.dimension for dimension, taxonomy in loaded.items()
        }
        mismatches = [
            f"{dimension}->{actual}"
            for dimension, actual in expected_dimensions.items()
            if dimension != actual
        ]
        if mismatches:
            raise ValueError("semantic task ontology dimension mismatch: " + ", ".join(mismatches))
        metadata["ontologies"] = references
        metadata["taxonomy"] = tuple(
            loaded.get("statement_functions").values if "statement_functions" in loaded else ()
        )
        metadata["knowledge_taxonomy"] = tuple(
            loaded.get("knowledge_kinds").values if "knowledge_kinds" in loaded else ()
        )
        metadata["process_taxonomy"] = tuple(
            loaded.get("process_functions").values if "process_functions" in loaded else ()
        )
        metadata["applicability_taxonomy"] = tuple(
            loaded.get("applicability_functions").values
            if "applicability_functions" in loaded
            else ()
        )
        metadata["role_relation_taxonomy"] = tuple(
            loaded.get("role_relation_types").values if "role_relation_types" in loaded else ()
        )
        schema = json.loads((root / "schema.json").read_text(encoding="utf-8"))
        return SemanticTaskDefinition.model_validate(metadata), schema


class ProposalRunConfig(BaseModel):
    """Configuration of one resumable proposal generation run."""

    model_config = ConfigDict(frozen=True)

    corpus_id: str = Field(min_length=1)
    task: str = Field(min_length=1)
    task_version: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(default=DEFAULT_EVALUATION_TEMPERATURE, ge=0.0, le=2.0)
    seed: int | None = DEFAULT_EVALUATION_SEED
    max_tokens: int = Field(default=DEFAULT_EVALUATION_MAX_TOKENS, gt=0)
    overwrite: bool = False
    limit: int | None = Field(default=None, gt=0)
    retry_attempts: int = Field(default=DEFAULT_EVALUATION_RETRY_ATTEMPTS, ge=1)
    retry_backoff_seconds: float = Field(default=DEFAULT_EVALUATION_RETRY_BACKOFF_SECONDS, ge=0.0)
    retry_timeouts: bool = DEFAULT_EVALUATION_RETRY_TIMEOUTS
    adaptive_interview: bool = False
    include_example_ids: tuple[str, ...] | None = None
    adaptive_question_max_tokens: int | None = Field(default=None, gt=0)
    truncation_retry_max_tokens: int | None = Field(default=None, gt=0)
    retry_on_truncation: bool = True
    reasoning_enabled: bool = False


@dataclass(frozen=True)
class ProposalRunResult:
    generated: int
    skipped: int
    failed: int
    run_directory: Path
    errors: tuple[str, ...]
    fresh_predictions: int = 0
    cached_predictions: int = 0
    reused_predictions: int = 0
    ineligible_predictions: int = 0
    fresh_inference_duration_seconds: float | None = None


def proposal_run_directory(config: ProposalRunConfig, output_root: Path) -> Path:
    """Return the deterministic directory of a proposal run."""
    return (
        output_root
        / "runs"
        / config.corpus_id
        / config.prompt_version
        / _safe(config.provider)
        / _safe(config.model)
    )


def historical_inference_duration(
    run_directory: Path, example_ids: tuple[str, ...] | list[str]
) -> tuple[int, float | None]:
    """Recover stored provider inference durations for reused proposal responses.

    ``duration_ms`` in an LLM cache entry is the duration of the original provider
    inference, not the cache lookup. Reusing it therefore preserves the last measured
    inference performance without timing the resume/recompute bookkeeping path.
    """
    measured = 0
    duration_seconds = 0.0
    for example_id in example_ids:
        response_path = run_directory / _safe(example_id) / "response.json"
        if not response_path.is_file():
            continue
        try:
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            duration_ms = payload.get("duration_ms")
            if duration_ms is None:
                continue
            duration_seconds += float(duration_ms) / 1000.0
            measured += 1
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return measured, duration_seconds if measured else None


class BaselineProposalGenerator:
    """Generate annotation proposals while preserving every request and response."""

    def __init__(self, gateway: LlmGateway) -> None:
        self._gateway = gateway

    def run(
        self,
        config: ProposalRunConfig,
        *,
        resources: Path,
        corpus_root: Path,
        output_root: Path,
        progress: ProposalProgressReporter | None = None,
    ) -> ProposalRunResult:
        task, canonical_schema = SemanticTaskRepository(resources / "tasks").load(
            config.task, config.task_version
        )
        prompt = PromptRepository(resources / "prompts").load(config.task, config.prompt_version)
        if dict(prompt.output_schema) != canonical_schema:
            raise ValueError("prompt schema differs from the canonical task schema")
        dataset = EvaluationDatasetRepository(corpus_root).load(config.task, config.dataset_version)
        all_examples = dataset.examples
        eligibility_policy = SemanticTaskEligibilityPolicy.from_task(task)
        run_dir = proposal_run_directory(config, output_root)
        pending = []
        skipped = 0
        reused_predictions = 0
        ineligible_predictions = 0
        included = set(config.include_example_ids or ())
        for example in all_examples:
            if included and example.id not in included:
                continue
            case_dir = run_dir / _safe(example.id)
            eligibility = eligibility_from_input(eligibility_policy, dict(example.input))
            if not eligibility.eligible:
                case_dir.mkdir(parents=True, exist_ok=True)
                _write_json(case_dir / "eligibility.json", eligibility.model_dump(mode="json"))
                skipped += 1
                ineligible_predictions += 1
                continue
            evaluation_path = case_dir / "evaluation.yaml"
            if evaluation_path.exists() and not config.overwrite:
                skipped += 1
                reused_predictions += 1
                continue
            pending.append(example)
            if config.limit is not None and len(pending) >= config.limit:
                break

        def process_example(current, total, example):
            status = "failed"
            error_message = None
            context = _progress_context(example.input)
            started_at = time.monotonic()
            case_dir = run_dir / _safe(example.id)
            case_dir.mkdir(parents=True, exist_ok=True)
            request = build_proposal_request(config, prompt, example.input, task)
            request_payload = serialize_generation_request(request)
            request_diagnostics = _request_diagnostics(request_payload)
            fresh_predictions = 0
            cached_predictions = 0
            fresh_inference_duration_seconds = 0.0
            _write_json(case_dir / "request.json", request_payload)
            if progress is not None:
                progress(
                    ProposalProgress(
                        current=current,
                        total=total,
                        example_id=example.id,
                        status="processing",
                        detail=_diagnostic_summary(request_diagnostics),
                        **context,
                    )
                )
            try:
                clause = build_clause_reference(example.input)

                report_retry = None
                if progress is not None:
                    report_retry = partial(
                        _report_retry_progress,
                        progress=progress,
                        current=current,
                        total=total,
                        example_id=example.id,
                        started_at=started_at,
                        max_attempts=config.retry_attempts,
                        context=context,
                    )

                interview_payload = None
                use_adaptive_interview = (
                    config.adaptive_interview
                    and _adaptive_interview_supports_schema(canonical_schema)
                )
                if use_adaptive_interview:
                    result, normalized_value, interview_payload = _run_adaptive_interview(
                        self._gateway,
                        config=config,
                        prompt=prompt,
                        item_input=example.input,
                        task=task,
                        attempts=config.retry_attempts,
                        backoff_seconds=config.retry_backoff_seconds,
                        retry_timeouts=config.retry_timeouts,
                        on_retry=report_retry,
                    )
                    _write_json(case_dir / "interview.json", interview_payload)
                    execution = interview_payload.get("execution", {})
                    fresh_predictions = int(execution.get("fresh_predictions", 0))
                    cached_predictions = int(execution.get("cached_predictions", 0))
                    fresh_inference_duration_seconds = float(
                        execution.get("fresh_inference_duration_seconds", 0.0)
                    )
                else:
                    result = generate_with_retry(
                        self._gateway,
                        request,
                        attempts=config.retry_attempts,
                        backoff_seconds=config.retry_backoff_seconds,
                        retry_timeouts=config.retry_timeouts,
                        on_retry=report_retry,
                        truncation_retry_max_tokens=config.truncation_retry_max_tokens,
                        retry_on_truncation=config.retry_on_truncation,
                    )
                    normalized_value = _normalize_selection_payload(
                        result.value, required_fields=canonical_schema.get("required", ())
                    )
                    if result.cached:
                        cached_predictions = 1
                    else:
                        fresh_predictions = 1
                        fresh_inference_duration_seconds = result.duration_ms / 1000.0
                response_payload = {
                    "value": dict(result.value),
                    "provider": result.provider,
                    "model": result.model,
                    "prompt_version": result.prompt_version,
                    "input_hash": result.input_hash,
                    "raw_response_hash": result.raw_response_hash,
                    "duration_ms": result.duration_ms,
                    "cached": result.cached,
                    "usage": vars(result.usage) if result.usage else None,
                    "raw_response": result.raw_response,
                }
                _write_json(case_dir / "response.json", response_payload)
                valid, error = validate_schema(normalized_value, canonical_schema)
                if not valid:
                    raise ValueError(f"provider response violates task schema: {error}")
                selection = StatementFunctionSelection.model_validate(normalized_value)
                annotation = ClauseEvaluationAnnotation(
                    task=config.task,
                    lifecycle_status=AnnotationLifecycleStatus.PROPOSED,
                    clause=clause,
                    proposal=selection,
                    generator=AnnotationGenerator(
                        provider=result.provider,
                        model=result.model,
                        prompt_id=config.prompt_version,
                        task_version=config.task_version,
                        temperature=config.temperature,
                        seed=config.seed,
                        input_hash=result.input_hash,
                        raw_response_hash=result.raw_response_hash,
                        generated_at=datetime.now(UTC),
                    ),
                )
                evaluation_payload = {
                    "schema_version": "1.0",
                    "kind": "semantic_evaluation",
                    "run": {
                        "corpus_id": config.corpus_id,
                        "task": config.task,
                        "task_version": config.task_version,
                        "dataset_version": config.dataset_version,
                        "prompt_version": config.prompt_version,
                        "provider": config.provider,
                        "model": config.model,
                    },
                    "annotation_candidate": annotation.model_dump(mode="json", exclude_none=True),
                }
                (case_dir / "evaluation.yaml").write_text(
                    yaml.safe_dump(evaluation_payload, sort_keys=False, allow_unicode=True),
                    encoding="utf-8",
                )
                status = "generated"
            except Exception as exc:  # keep long runs resumable
                elapsed_seconds = time.monotonic() - started_at
                error = f"{example.id}: {type(exc).__name__}: {exc}"
                error_message = error
                detail = _error_summary(exc)
                failure_payload = {
                    "clause": {"id": example.id, **context},
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "category": _error_category(exc),
                    },
                    "elapsed_seconds": round(elapsed_seconds, 3),
                    "request": request_diagnostics,
                }
                raw_content = getattr(exc, "raw_content", None)
                raw_response = getattr(exc, "raw_response", None)
                finish_reason = getattr(exc, "finish_reason", None)
                if finish_reason is not None:
                    failure_payload["error"]["finish_reason"] = finish_reason
                if raw_content is not None:
                    (case_dir / "response.txt").write_text(raw_content, encoding="utf-8")
                    failure_payload["response"] = {
                        "content_file": "response.txt",
                        "content_chars": len(raw_content),
                        "content_preview": _content_preview(raw_content),
                    }
                if raw_response is not None:
                    _write_json(case_dir / "response.json", raw_response)
                    failure_payload.setdefault("response", {})["raw_response_file"] = (
                        "response.json"
                    )
                _write_json(case_dir / "failure.json", failure_payload)
            else:
                detail = None
            finally:
                if progress is not None:
                    progress(
                        ProposalProgress(
                            current=current,
                            total=total,
                            example_id=example.id,
                            status=status,
                            detail=detail,
                            elapsed_seconds=time.monotonic() - started_at,
                            **context,
                        )
                    )
            return ProposalItemOutcome(
                status == "generated",
                error_message,
                fresh_predictions=fresh_predictions,
                cached_predictions=cached_predictions,
                fresh_inference_duration_seconds=fresh_inference_duration_seconds,
            )

        batch = ProposalBatchExecutor().execute(pending, process_example)
        generated = batch.generated
        failed = batch.failed
        errors = list(batch.errors)
        _write_json(
            run_dir / "run.json",
            {
                "config": config.model_dump(mode="json"),
                "generated": generated,
                "skipped": skipped,
                "failed": failed,
                "errors": errors,
                "execution": {
                    "fresh_predictions": batch.fresh_predictions,
                    "cached_predictions": batch.cached_predictions,
                    "reused_predictions": reused_predictions,
                    "ineligible_predictions": ineligible_predictions,
                    "fresh_inference_duration_seconds": (
                        batch.fresh_inference_duration_seconds if batch.fresh_predictions else None
                    ),
                },
            },
        )
        return ProposalRunResult(
            generated,
            skipped,
            failed,
            run_dir,
            tuple(errors),
            fresh_predictions=batch.fresh_predictions,
            cached_predictions=batch.cached_predictions,
            reused_predictions=reused_predictions,
            ineligible_predictions=ineligible_predictions,
            fresh_inference_duration_seconds=(
                batch.fresh_inference_duration_seconds if batch.fresh_predictions else None
            ),
        )


def _adaptive_interview_supports_schema(schema: Mapping[str, Any]) -> bool:
    """Return whether the interview aggregator can satisfy the task schema.

    The current adaptive interview only classifies scalar/multi-label ontology
    dimensions. It does not extract structured role relation objects (actor, relation_class,
    target). When ``role_relations`` is required
    by the canonical task schema, using the interview would therefore construct
    a response that can never satisfy that contract. Fall back to the direct
    structured-generation path until the interview has a dedicated extraction
    step for role relations.
    """
    return "role_relations" not in set(schema.get("required", ()))


def _run_adaptive_interview(
    gateway: LlmGateway,
    *,
    config: ProposalRunConfig,
    prompt,
    item_input,
    task: SemanticTaskDefinition,
    attempts: int,
    backoff_seconds: float,
    retry_timeouts: bool,
    on_retry,
):
    content = dict(item_input.get("content", {}))
    full_context = dict(item_input.get("context", {}))
    context = full_context if "{context_json}" in prompt.user_template else {}
    interview_input = {**dict(item_input), "context": context}
    plan = AdaptiveInterviewPlanner().plan(interview_input)
    answers: list[dict[str, Any]] = []
    last_result = None
    fresh_predictions = 0
    cached_predictions = 0
    fresh_inference_duration_seconds = 0.0
    selection: dict[str, Any] = {
        "statement_functions": [],
        "primary_function": None,
        "knowledge_kinds": [],
        "primary_knowledge_kind": None,
        "process_functions": [],
        "primary_process_function": None,
        "applicability_functions": [],
        "primary_applicability_function": None,
        "role_relation_types": [],
        "primary_role_relation_type": None,
        "confidence": None,
        "rationale": None,
    }
    confidences: list[float] = []
    rationales: list[str] = []
    pending_questions = list(plan.questions)
    while pending_questions:
        question = pending_questions.pop(0)
        request = StructuredGenerationRequest(
            task=f"{config.task}:{question.id}",
            system_prompt=(
                "Answer exactly one focused taxonomy question. Use only the normalized "
                "content and supplied structural context. Select 'none' or 'unclear' when "
                "the evidence is insufficient. Return JSON matching the schema."
            ),
            user_prompt=(
                f"Question: {question.question}\n"
                f"Allowed labels: {', '.join(question.allowed_labels)}\n"
                f"Selection reason: {question.reason}\n\n"
                f"Normalized clause content:\n{content.get('text', '')}\n\n"
                f"Structural context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}"
            ),
            output_schema=focused_response_schema(question.allowed_labels),
            prompt_version=f"{config.prompt_version}:{question.id}",
            model=config.model,
            temperature=config.temperature,
            seed=config.seed,
            max_tokens=config.adaptive_question_max_tokens or config.max_tokens,
            reasoning_enabled=config.reasoning_enabled,
            metadata={
                "corpus_id": config.corpus_id,
                "dataset_version": config.dataset_version,
                "task_version": task.version,
                "content_hash": content.get("hash"),
                "clause_context": context,
                "interview_question": question.model_dump(mode="json"),
            },
        )
        result = generate_with_retry(
            gateway,
            request,
            attempts=attempts,
            backoff_seconds=backoff_seconds,
            retry_timeouts=retry_timeouts,
            on_retry=on_retry,
            truncation_retry_max_tokens=config.truncation_retry_max_tokens,
            retry_on_truncation=config.retry_on_truncation,
        )
        last_result = result
        if result.cached:
            cached_predictions += 1
        else:
            fresh_predictions += 1
            fresh_inference_duration_seconds += result.duration_ms / 1000.0
        answer = dict(result.value)
        label = str(answer["label"])
        confidence = float(answer["confidence"])
        evidence = str(answer["evidence"])
        answers.append({"question": question.model_dump(mode="json"), "answer": answer})
        confidences.append(confidence)
        if evidence:
            rationales.append(f"{question.id}: {evidence}")
        if label == "present":
            follow_up = follow_up_question(question)
            if follow_up is not None:
                pending_questions.insert(0, follow_up)
            continue
        if label in {"none", "unclear"}:
            continue
        if question.dimension is InterviewDimension.STATEMENT_FUNCTION:
            selection["statement_functions"] = [label]
            selection["primary_function"] = label
        elif question.dimension is InterviewDimension.KNOWLEDGE_KIND:
            selection["knowledge_kinds"] = [label]
            selection["primary_knowledge_kind"] = label
        elif question.dimension is InterviewDimension.PROCESS_FUNCTION:
            selection["process_functions"] = [label]
            selection["primary_process_function"] = label
        elif question.dimension is InterviewDimension.APPLICABILITY:
            selection["applicability_functions"] = [label]
            selection["primary_applicability_function"] = label
        elif question.dimension is InterviewDimension.ROLE_RELATION:
            selection["role_relation_types"] = [label]
            selection["primary_role_relation_type"] = label
    selection["confidence"] = min(confidences) if confidences else None
    selection["rationale"] = " | ".join(rationales) or None
    if last_result is None:
        # Structural evidence made every dimension deterministic. Preserve a valid result-like
        # object by falling back to the original prompt for one compatibility request.
        last_result = generate_with_retry(
            gateway,
            build_proposal_request(config, prompt, item_input, task),
            attempts=attempts,
            backoff_seconds=backoff_seconds,
            retry_timeouts=retry_timeouts,
            on_retry=on_retry,
            truncation_retry_max_tokens=config.truncation_retry_max_tokens,
            retry_on_truncation=config.retry_on_truncation,
        )
        if last_result.cached:
            cached_predictions += 1
        else:
            fresh_predictions += 1
            fresh_inference_duration_seconds += last_result.duration_ms / 1000.0
        selection = _normalize_selection_payload(
            last_result.value,
            required_fields=(
                "knowledge_kinds",
                "primary_knowledge_kind",
                "process_functions",
                "primary_process_function",
                "applicability_functions",
                "primary_applicability_function",
                "role_relation_types",
                "primary_role_relation_type",
            ),
        )
    return (
        last_result,
        selection,
        {
            "plan": plan.model_dump(mode="json"),
            "answers": answers,
            "aggregated_selection": selection,
            "execution": {
                "fresh_predictions": fresh_predictions,
                "cached_predictions": cached_predictions,
                "fresh_inference_duration_seconds": fresh_inference_duration_seconds,
            },
        },
    )


def _report_retry_progress(
    attempt: int,
    error: LlmUnavailableError,
    *,
    progress: ProposalProgressReporter,
    current: int,
    total: int,
    example_id: str,
    started_at: float,
    max_attempts: int,
    context: dict[str, Any],
) -> None:
    progress(
        ProposalProgress(
            current=current,
            total=total,
            example_id=example_id,
            status="retrying",
            detail=_error_summary(error),
            elapsed_seconds=time.monotonic() - started_at,
            attempt=attempt,
            max_attempts=max_attempts,
            **context,
        )
    )


def _progress_context(item_input: Any) -> dict[str, Any]:
    context = dict(item_input.get("context", {}))
    return {
        "document_key": str(context.get("document_key", "unknown-document")),
        "reference": context.get("reference"),
        "title": context.get("title"),
    }


def _error_summary(error: Exception) -> str:
    message = " ".join(str(error).split())
    if len(message) > 240:
        message = message[:237] + "..."
    return f"{type(error).__name__}: {message}"


def _request_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {
        "request_hash": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        "request_bytes": len(canonical),
        "system_prompt_chars": len(str(payload.get("system_prompt", ""))),
        "user_prompt_chars": len(str(payload.get("user_prompt", ""))),
        "max_tokens": payload.get("max_tokens"),
    }


def _diagnostic_summary(diagnostics: dict[str, Any]) -> str:
    return (
        f"request={diagnostics['request_hash'][:19]}… "
        f"prompt={diagnostics['user_prompt_chars']} chars "
        f"max_tokens={diagnostics['max_tokens']}"
    )


def _error_category(error: Exception) -> str:
    if isinstance(error, LlmTimeoutError):
        return "generation_timeout"
    if isinstance(error, LlmUnavailableError):
        return "provider_unavailable"
    if isinstance(error, LlmResponseError):
        if error.finish_reason == "length":
            raw_response = error.raw_response
            if isinstance(raw_response, dict):
                choices = raw_response.get("choices", ())
                if choices and isinstance(choices[0], dict):
                    message = choices[0].get("message", {})
                    if isinstance(message, dict):
                        content = str(message.get("content") or "").strip()
                        reasoning = str(message.get("reasoning_content") or "").strip()
                        if reasoning and not content:
                            return "truncated_reasoning"
            return "truncated_response"
        return "invalid_provider_response"
    if isinstance(error, ValueError):
        return "validation_error"
    return "unexpected_error"


def _content_preview(content: str, limit: int = 1000) -> str:
    compact = " ".join(content.split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."


def _normalize_selection_payload(
    value: Any, *, required_fields: tuple[str, ...] | list[str] = ()
) -> dict[str, Any]:
    """Canonicalize harmless provider variance before strict domain validation."""
    if not isinstance(value, dict):
        return dict(value)
    normalized = dict(value)
    supplied_fields = set(normalized)
    defaults = {
        "knowledge_kinds": [],
        "primary_knowledge_kind": None,
        "process_functions": [],
        "primary_process_function": None,
        "applicability_functions": [],
        "primary_applicability_function": None,
        "role_relation_types": [],
        "primary_role_relation_type": None,
    }
    for field in required_fields:
        if field in defaults:
            normalized.setdefault(field, defaults[field])

    # ``role_relations`` was added after the scalar role-relation classification
    # fields. Older/smaller providers may omit the complete new dimension when
    # abstaining. Preserve the existing compatibility behaviour for missing
    # ontology dimensions by materializing an empty extraction only when the
    # provider either omitted the complete role-relation block or explicitly
    # returned an empty/null classification. Do not repair a positive or partial
    # classification that is missing its structured extraction.
    if "role_relations" in required_fields and "role_relations" not in normalized:
        role_types_supplied = "role_relation_types" in supplied_fields
        primary_role_supplied = "primary_role_relation_type" in supplied_fields
        complete_block_omitted = not role_types_supplied and not primary_role_supplied
        explicit_abstention = (
            role_types_supplied
            and primary_role_supplied
            and normalized.get("role_relation_types") in ([], ())
            and normalized.get("primary_role_relation_type") is None
        )
        if complete_block_omitted or explicit_abstention:
            normalized["role_relations"] = []

    roles = normalized.get("statement_functions")
    if isinstance(roles, (list, tuple)):
        normalized_roles = list(dict.fromkeys(roles))
        primary_function = normalized.get("primary_function")
        if primary_function is not None and primary_function not in normalized_roles:
            normalized_roles.insert(0, primary_function)
        normalized["statement_functions"] = normalized_roles
    for field, primary in (
        ("process_functions", "primary_process_function"),
        ("applicability_functions", "primary_applicability_function"),
        ("role_relation_types", "primary_role_relation_type"),
    ):
        values = normalized.get(field)
        if isinstance(values, (list, tuple)):
            normalized_values = list(dict.fromkeys(values))
            primary_value = normalized.get(primary)
            if primary_value is not None and primary_value not in normalized_values:
                normalized_values.insert(0, primary_value)
            normalized[field] = normalized_values
    return normalized


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _safe(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_." else "_" for character in value
    )
