"""Baseline proposal generation with durable requests and provider responses."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.evaluation.repository import (
    EvaluationDatasetRepository,
    PromptRepository,
)
from standards_atlas.application.evaluation.schema import validate_schema
from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
    StructuredGenerationRequest,
)
from standards_atlas.application.semantic_qualification.adaptive_interview import (
    AdaptiveInterviewPlanner,
    InterviewDimension,
    focused_response_schema,
)
from standards_atlas.application.semantic_qualification.annotations import (
    AnnotationGenerator,
    AnnotationLifecycleStatus,
    ClauseEvaluationAnnotation,
    ClauseReference,
    StatementFunctionSelection,
)
from standards_atlas.application.semantic_qualification.defaults import (
    DEFAULT_EVALUATION_MAX_TOKENS,
    DEFAULT_EVALUATION_RETRY_ATTEMPTS,
    DEFAULT_EVALUATION_RETRY_BACKOFF_SECONDS,
    DEFAULT_EVALUATION_RETRY_TIMEOUTS,
    DEFAULT_EVALUATION_SEED,
    DEFAULT_EVALUATION_TEMPERATURE,
)


class SemanticTaskDefinition(BaseModel):
    """Versioned semantic task contract."""

    model_config = ConfigDict(frozen=True)

    task: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = ""
    taxonomy: tuple[str, ...] = ()
    applicability_taxonomy: tuple[str, ...] = ()
    responsibility_taxonomy: tuple[str, ...] = ()
    multi_label: bool = True
    allow_unclassified: bool = True


class SemanticTaskRepository:
    """Load task metadata, taxonomy, and the canonical output schema."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def load(self, task: str, version: str) -> tuple[SemanticTaskDefinition, dict[str, Any]]:
        root = self._root / task / version
        metadata = yaml.safe_load((root / "task.yaml").read_text(encoding="utf-8")) or {}
        taxonomy = yaml.safe_load((root / "taxonomy.yaml").read_text(encoding="utf-8")) or {}
        metadata["taxonomy"] = tuple(taxonomy.get("statement_functions", taxonomy.get("roles", ())))
        metadata["applicability_taxonomy"] = tuple(taxonomy.get("applicability_functions", ()))
        metadata["responsibility_taxonomy"] = tuple(taxonomy.get("responsibility_functions", ()))
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
    adaptive_question_max_tokens: int | None = Field(default=None, gt=0)
    truncation_retry_max_tokens: int | None = Field(default=None, gt=0)
    retry_on_truncation: bool = True
    reasoning_enabled: bool = False


@dataclass(frozen=True)
class ProposalProgress:
    current: int
    total: int
    example_id: str
    status: str
    document_key: str
    reference: str | None
    title: str | None
    detail: str | None = None
    elapsed_seconds: float | None = None
    attempt: int | None = None
    max_attempts: int | None = None


@dataclass(frozen=True)
class ProposalRunResult:
    generated: int
    skipped: int
    failed: int
    run_directory: Path
    errors: tuple[str, ...]


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
        progress: Callable[[ProposalProgress], None] | None = None,
    ) -> ProposalRunResult:
        task, canonical_schema = SemanticTaskRepository(resources / "tasks").load(
            config.task, config.task_version
        )
        prompt = PromptRepository(resources / "prompts").load(config.task, config.prompt_version)
        if dict(prompt.output_schema) != canonical_schema:
            raise ValueError("prompt schema differs from the canonical task schema")
        dataset = EvaluationDatasetRepository(corpus_root).load(config.task, config.dataset_version)
        all_examples = dataset.examples
        run_dir = proposal_run_directory(config, output_root)
        pending = []
        skipped = 0
        for example in all_examples:
            case_dir = run_dir / _safe(example.id)
            evaluation_path = case_dir / "evaluation.yaml"
            if evaluation_path.exists() and not config.overwrite:
                skipped += 1
                continue
            pending.append(example)
            if config.limit is not None and len(pending) >= config.limit:
                break

        generated = failed = 0
        errors: list[str] = []
        total = len(pending)
        for current, example in enumerate(pending, start=1):
            status = "failed"
            context = _progress_context(example.input)
            started_at = time.monotonic()
            case_dir = run_dir / _safe(example.id)
            case_dir.mkdir(parents=True, exist_ok=True)
            request = _request(config, prompt, example.input, task)
            request_payload = _request_payload(request)
            request_diagnostics = _request_diagnostics(request_payload)
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
                clause = _clause_reference(example.input)

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
                if config.adaptive_interview:
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
                else:
                    result = _generate_with_retry(
                        self._gateway,
                        request,
                        attempts=config.retry_attempts,
                        backoff_seconds=config.retry_backoff_seconds,
                        retry_timeouts=config.retry_timeouts,
                        on_retry=report_retry,
                        truncation_retry_max_tokens=config.truncation_retry_max_tokens,
                        retry_on_truncation=config.retry_on_truncation,
                    )
                    normalized_value = _normalize_selection_payload(result.value)
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
                generated += 1
                status = "generated"
            except Exception as exc:  # keep long runs resumable
                failed += 1
                elapsed_seconds = time.monotonic() - started_at
                error = f"{example.id}: {type(exc).__name__}: {exc}"
                errors.append(error)
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
        _write_json(
            run_dir / "run.json",
            {
                "config": config.model_dump(mode="json"),
                "generated": generated,
                "skipped": skipped,
                "failed": failed,
                "errors": errors,
            },
        )
        return ProposalRunResult(generated, skipped, failed, run_dir, tuple(errors))


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
    plan = AdaptiveInterviewPlanner().plan(item_input)
    content = dict(item_input.get("content", {}))
    context = dict(item_input.get("context", {}))
    answers: list[dict[str, Any]] = []
    last_result = None
    selection: dict[str, Any] = {
        "statement_functions": [],
        "primary_function": None,
        "applicability_functions": [],
        "primary_applicability_function": None,
        "responsibility_functions": [],
        "primary_responsibility_function": None,
        "confidence": None,
        "rationale": None,
    }
    confidences: list[float] = []
    rationales: list[str] = []
    for question in plan.questions:
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
        result = _generate_with_retry(
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
        answer = dict(result.value)
        label = str(answer["label"])
        confidence = float(answer["confidence"])
        evidence = str(answer["evidence"])
        answers.append({"question": question.model_dump(mode="json"), "answer": answer})
        confidences.append(confidence)
        if evidence:
            rationales.append(f"{question.id}: {evidence}")
        if label in {"none", "unclear"}:
            continue
        if question.dimension is InterviewDimension.STATEMENT_FUNCTION:
            selection["statement_functions"] = [label]
            selection["primary_function"] = label
        elif question.dimension is InterviewDimension.APPLICABILITY:
            selection["applicability_functions"] = [label]
            selection["primary_applicability_function"] = label
        elif question.dimension is InterviewDimension.RESPONSIBILITY:
            selection["responsibility_functions"] = [label]
            selection["primary_responsibility_function"] = label
    selection["confidence"] = min(confidences) if confidences else None
    selection["rationale"] = " | ".join(rationales) or None
    if last_result is None:
        # Structural evidence made every dimension deterministic. Preserve a valid result-like
        # object by falling back to the original prompt for one compatibility request.
        last_result = _generate_with_retry(
            gateway,
            _request(config, prompt, item_input, task),
            attempts=attempts,
            backoff_seconds=backoff_seconds,
            retry_timeouts=retry_timeouts,
            on_retry=on_retry,
            truncation_retry_max_tokens=config.truncation_retry_max_tokens,
            retry_on_truncation=config.retry_on_truncation,
        )
        selection = _normalize_selection_payload(last_result.value)
    return (
        last_result,
        selection,
        {
            "plan": plan.model_dump(mode="json"),
            "answers": answers,
            "aggregated_selection": selection,
        },
    )


def _report_retry_progress(
    attempt: int,
    error: LlmUnavailableError,
    *,
    progress: Callable[[ProposalProgress], None],
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


def _generate_with_retry(
    gateway: LlmGateway,
    request: StructuredGenerationRequest,
    *,
    attempts: int,
    backoff_seconds: float,
    retry_timeouts: bool = DEFAULT_EVALUATION_RETRY_TIMEOUTS,
    on_retry: Callable[[int, Exception], None] | None = None,
    truncation_retry_max_tokens: int | None = None,
    retry_on_truncation: bool = True,
):
    """Retry transient failures and one truncated response with a larger budget."""
    active_request = request
    transient_attempt = 1
    truncation_retried = False
    while True:
        try:
            return gateway.generate_structured(active_request)
        except LlmResponseError as error:
            can_retry_truncation = (
                retry_on_truncation
                and not truncation_retried
                and error.finish_reason == "length"
                and truncation_retry_max_tokens is not None
                and (active_request.max_tokens or 0) < truncation_retry_max_tokens
            )
            if not can_retry_truncation:
                raise
            truncation_retried = True
            active_request = replace(
                active_request,
                max_tokens=truncation_retry_max_tokens,
                reasoning_enabled=False,
            )
            if on_retry is not None:
                on_retry(transient_attempt, error)
        except LlmUnavailableError as error:
            if isinstance(error, LlmTimeoutError) and not retry_timeouts:
                raise
            if transient_attempt >= attempts:
                raise
            if on_retry is not None:
                on_retry(transient_attempt, error)
            if backoff_seconds:
                time.sleep(backoff_seconds * transient_attempt)
            transient_attempt += 1


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


def _normalize_selection_payload(value: Any) -> dict[str, Any]:
    """Canonicalize harmless provider variance before strict domain validation."""
    if not isinstance(value, dict):
        return dict(value)
    normalized = dict(value)
    roles = normalized.get("statement_functions")
    if isinstance(roles, (list, tuple)):
        normalized_roles = list(dict.fromkeys(roles))
        primary_function = normalized.get("primary_function")
        if primary_function is not None and primary_function not in normalized_roles:
            normalized_roles.insert(0, primary_function)
        normalized["statement_functions"] = normalized_roles
    for field, primary in (
        ("applicability_functions", "primary_applicability_function"),
        ("responsibility_functions", "primary_responsibility_function"),
    ):
        values = normalized.get(field)
        if isinstance(values, (list, tuple)):
            normalized_values = list(dict.fromkeys(values))
            primary_value = normalized.get(primary)
            if primary_value is not None and primary_value not in normalized_values:
                normalized_values.insert(0, primary_value)
            normalized[field] = normalized_values
    return normalized


def _request(config, prompt, item_input, task):
    content = dict(item_input.get("content", {}))
    context = dict(item_input.get("context", {}))
    values = {
        "content": content.get("text", ""),
        "content_hash": content.get("hash", ""),
        "context_json": json.dumps(context, ensure_ascii=False, sort_keys=True),
        **context,
    }
    try:
        user_prompt = prompt.user_template.format(**values)
    except KeyError as exc:
        raise ValueError(f"prompt references unavailable field: {exc.args[0]}") from exc
    return StructuredGenerationRequest(
        task=config.task,
        system_prompt=prompt.system_prompt,
        user_prompt=user_prompt,
        output_schema=prompt.output_schema,
        prompt_version=config.prompt_version,
        model=config.model,
        temperature=config.temperature,
        seed=config.seed,
        max_tokens=config.max_tokens,
        reasoning_enabled=config.reasoning_enabled,
        metadata={
            "corpus_id": config.corpus_id,
            "dataset_version": config.dataset_version,
            "task_version": task.version,
            "content_hash": content.get("hash"),
            "clause_context": context,
        },
    )


def _clause_reference(item_input) -> ClauseReference:
    content = dict(item_input["content"])
    context = dict(item_input["context"])
    return ClauseReference(
        knowledge_domain=context["knowledge_domain"],
        document_key=context["document_key"],
        clause_id=context["clause_id"],
        content_hash=content["hash"],
    )


def _request_payload(request: StructuredGenerationRequest) -> dict[str, Any]:
    return {
        "task": request.task,
        "system_prompt": request.system_prompt,
        "user_prompt": request.user_prompt,
        "output_schema": dict(request.output_schema),
        "prompt_version": request.prompt_version,
        "model": request.model,
        "temperature": request.temperature,
        "seed": request.seed,
        "max_tokens": request.max_tokens,
        "reasoning_enabled": request.reasoning_enabled,
        "metadata": dict(request.metadata),
    }


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
