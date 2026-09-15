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
from typing import Any, ClassVar, Literal

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
from standards_atlas.application.schema import require_current_payload, require_supported_schema
from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.application.semantic_ontology import (
    OntologyReference,
    ResourceOntologyDefinitionRepository,
)
from standards_atlas.application.semantic_qualification.annotations import (
    AnnotationGenerator,
    AnnotationLifecycleStatus,
    ApplicabilityPresenceSelection,
    ClauseEvaluationAnnotation,
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
from standards_atlas.application.semantic_qualification.performance import (
    MeasuredLlmGateway,
    RequestTiming,
    measured_seconds,
    stored_request_timing,
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


class SemanticTaskDefinition(SchemaBoundModel):
    """Versioned semantic task contract."""

    SCHEMA_FAMILY: ClassVar[str] = "semantic-task-resource"

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    task: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = ""
    canonical_task: str | None = None
    aliases: tuple[str, ...] = ()
    ontologies: dict[str, OntologyReference] = Field(default_factory=dict)
    applicability_taxonomy: tuple[str, ...] = ()
    applicability_target_taxonomy: tuple[str, ...] = ()
    other_applicability_target_taxonomy: tuple[str, ...] = ()
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
        metadata["applicability_taxonomy"] = tuple(
            loaded.get("applicability_functions").values
            if "applicability_functions" in loaded
            else ()
        )
        metadata["applicability_target_taxonomy"] = tuple(
            loaded.get("applicability_targets").values if "applicability_targets" in loaded else ()
        )
        metadata["other_applicability_target_taxonomy"] = tuple(
            loaded.get("other_applicability_targets").values
            if "other_applicability_targets" in loaded
            else ()
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
    cbox_frame: str = Field(default="full-context-v1", min_length=1)
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
    include_example_ids: tuple[str, ...] | None = None
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
    request_timing: RequestTiming | None = None


def proposal_run_directory(config: ProposalRunConfig, output_root: Path) -> Path:
    """Return the deterministic directory of a proposal run."""
    return (
        output_root
        / "runs"
        / config.corpus_id
        / config.prompt_version
        / _safe(config.cbox_frame)
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
        case_dir = run_directory / _safe(example_id)
        timing_path = case_dir / "request-timing.json"
        try:
            if timing_path.is_file():
                timing = stored_request_timing(timing_path)
                measured += timing.measured_request_count
                duration_seconds += timing.recorded_inference_duration_seconds or 0.0
                continue
            # Old adaptive reports expose only the final response, not a
            # per-request total. Do not treat that as the entire interview.
            if (case_dir / "interview.json").is_file():
                continue
            if (case_dir / "failure.json").is_file():
                continue  # May retain a stale response from an older proposal.
            response_path = case_dir / "response.json"
            if not response_path.is_file():
                continue
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            value = measured_seconds(payload.get("duration_ms"))
            if value is not None:
                duration_seconds += value
                measured += 1
        except (OSError, TypeError, ValueError):
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
        if config.task == "semantic-attribute-observation":
            raise ValueError("experimental partial task must use evaluation partial-proposals")
        task, canonical_schema = SemanticTaskRepository(resources / "tasks").load(
            config.task, config.task_version
        )
        prompt = PromptRepository(resources / "prompts").load(config.task, config.prompt_version)
        if not _prompt_schema_is_compatible(dict(prompt.output_schema), canonical_schema):
            raise ValueError("prompt schema is not a safe narrowing of the canonical task schema")
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
                current_request = build_proposal_request(config, prompt, example.input, task)
                if _proposal_inputs_match(case_dir, current_request):
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
            # Never leave a formerly successful but now stale evaluation visible
            # if the replacement request fails or the process is interrupted.
            (case_dir / "evaluation.yaml").unlink(missing_ok=True)
            request = build_proposal_request(config, prompt, example.input, task)
            request_payload = serialize_generation_request(request)
            request_diagnostics = _request_diagnostics(request_payload)
            measured_gateway = MeasuredLlmGateway(self._gateway)
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

                result = generate_with_retry(
                    measured_gateway,
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
                selection = ApplicabilityPresenceSelection.model_validate(normalized_value)
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
                        provided_fields=tuple(sorted(result.value)),
                        generated_at=datetime.now(UTC),
                    ),
                )
                evaluation_payload = {
                    "schema_version": 1,
                    "kind": "semantic_evaluation",
                    "run": {
                        "corpus_id": config.corpus_id,
                        "task": config.task,
                        "task_version": config.task_version,
                        "dataset_version": config.dataset_version,
                        "prompt_version": config.prompt_version,
                        "cbox_frame": config.cbox_frame,
                        "provider": config.provider,
                        "model": config.model,
                    },
                    "annotation_candidate": annotation.model_dump(mode="json", exclude_none=True),
                }
                require_current_payload("semantic-evaluation", evaluation_payload)
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
                _write_json(
                    case_dir / "request-timing.json",
                    measured_gateway.timing.model_dump(mode="json"),
                )
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
                fresh_predictions=measured_gateway.timing.fresh_response_count,
                cached_predictions=measured_gateway.timing.cached_response_count,
                fresh_inference_duration_seconds=(
                    measured_gateway.timing.fresh_inference_duration_seconds or 0.0
                ),
                request_timing=measured_gateway.timing,
            )

        batch = ProposalBatchExecutor().execute(pending, process_example)
        execution_timing = batch.request_timing or RequestTiming()
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
                        execution_timing.fresh_inference_duration_seconds
                    ),
                    "request_timing": execution_timing.model_dump(mode="json"),
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
            fresh_inference_duration_seconds=(execution_timing.fresh_inference_duration_seconds),
            request_timing=execution_timing,
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
        "heading": context.get("heading") or context.get("title"),
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
    """Normalize the focused applicability-presence response before validation."""
    if not isinstance(value, dict):
        return dict(value)
    return dict(value)


def _prompt_schema_is_compatible(
    prompt_schema: Mapping[str, Any], canonical_schema: Mapping[str, Any]
) -> bool:
    """Require prompt and task schemas to describe the same focused contract."""
    return prompt_schema == canonical_schema


def _schema_path(schema: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = schema
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value


def _set_schema_path(schema: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    target = schema
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


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


def _proposal_inputs_match(case_dir: Path, request: StructuredGenerationRequest) -> bool:
    """Older requests without a verified input fingerprint are recomputed once."""
    try:
        stored = json.loads((case_dir / "request.json").read_text(encoding="utf-8"))
        fingerprint = stored["metadata"]["qualification_input_fingerprint"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return fingerprint == request.metadata["qualification_input_fingerprint"]
