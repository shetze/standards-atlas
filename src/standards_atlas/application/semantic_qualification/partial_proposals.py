"""Isolated, resumable partial inference; no consensus or public enrichment writes."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.ports.llm_gateway import LlmGateway
from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.batch import (
    ProposalBatchExecutor,
    ProposalItemOutcome,
)
from standards_atlas.application.semantic_qualification.cascade_replay_source import (
    CascadeReplaySource,
)
from standards_atlas.application.semantic_qualification.eligibility import (
    SemanticTaskEligibilityPolicy,
    eligibility_from_input,
)
from standards_atlas.application.semantic_qualification.partial_observations import (
    PartialObservation,
    observation_states,
    validate_partial_response,
)
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialProposalConfig,
    PartialTaskResources,
    PreparedPartialRequest,
    prepare_partial_request,
)
from standards_atlas.application.semantic_qualification.performance import (
    MeasuredLlmGateway,
    RequestTiming,
)
from standards_atlas.application.semantic_qualification.request_builder import (
    serialize_generation_request,
)
from standards_atlas.application.semantic_qualification.retry import generate_with_retry


@dataclass(frozen=True)
class PartialInputSelection:
    examples: tuple[EvaluationExample, ...]
    fingerprints: dict[str, str]
    corpus_id: str
    dataset_version: str


def load_partial_inputs(
    *, run: Path | None = None, dataset: Path | None = None
) -> PartialInputSelection:
    """Read source inputs only. Expected labels and tags never enter preparation."""
    if (run is None) == (dataset is None):
        raise ValueError("provide exactly one of --run or --dataset")
    if run is not None:
        source = CascadeReplaySource(run)
        try:
            selection = source.selection()
            with tempfile.TemporaryDirectory(prefix="atlas-partial-source-") as temporary:
                examples = source.materialize_inputs(selection, Path(temporary))
            fingerprints = dict(source.fingerprints)
            corpus_id, dataset_version = selection.corpus_id, selection.dataset_version
        finally:
            source.close()
    else:
        raw = dataset.read_bytes()
        payload = json.loads(raw)
        examples = tuple(
            EvaluationExample(id=item["id"], input=item["input"], expected={})
            for item in payload["examples"]
        )
        fingerprints = {str(dataset.resolve()): hashlib.sha256(raw).hexdigest()}
        corpus_id = str(payload.get("corpus_id") or "source-dataset")
        dataset_version = str(payload.get("version") or "unversioned-source")
    return PartialInputSelection(
        tuple(EvaluationExample(id=item.id, input=item.input, expected={}) for item in examples),
        fingerprints,
        corpus_id,
        dataset_version,
    )


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"refusing to replace symlink: {path}")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def _run_lock(root: Path):
    lock = root / ".partial-run.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            "partial run is locked; verify no writer is active before recovery"
        ) from exc
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


class _RecordingGateway:
    """Keep each attempt separate; the final logical observation is written once."""

    def __init__(self, gateway: LlmGateway, directory: Path):
        self.gateway = gateway
        self.directory = directory
        self.records: list[dict[str, Any]] = []

    def health(self):
        return self.gateway.health()

    def generate_structured(self, request):
        record = {"request": serialize_generation_request(request)}
        try:
            result = self.gateway.generate_structured(request)
            record["response"] = asdict(result)
            return result
        except BaseException as exc:
            # Record interruptions too, but never swallow them or turn them into votes.
            record["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
                "finish_reason": getattr(exc, "finish_reason", None),
                "raw_content": getattr(exc, "raw_content", None),
                "raw_response": getattr(exc, "raw_response", None),
            }
            raise
        finally:
            self.records.append(record)
            _atomic_json(self.directory / f"attempt-{len(self.records):03d}.json", record)


def _resume_observation(
    directory: Path, prepared: PreparedPartialRequest, config: PartialProposalConfig
) -> PartialObservation | None:
    path = directory / "partial-observation.json"
    if not path.is_file():
        return None
    payload = _read_json(path)
    require_supported_schema("partial-semantic-observation", payload.get("schema_version"))
    result = PartialObservation.model_validate(payload)
    if (
        result.plan.fingerprint != prepared.plan.fingerprint
        or result.request_fingerprint != prepared.fingerprint
        or result.provider != config.provider
        or result.model != config.model
    ):
        raise ValueError("stored partial observation has a different input identity")
    if result.outcome == "failed":
        return None
    if result.outcome == "evaluated":
        response = _read_json(directory / "response.json")
        if structure_fingerprint(response) != result.response_sha256:
            raise ValueError("partial response checksum mismatch")
        if response["value"] != result.values:
            raise ValueError("partial observation differs from its stored response")
        validate_partial_response(result.values, prepared.request.output_schema, prepared.plan)
    return result


def _execute_case(
    prepared: PreparedPartialRequest,
    config: PartialProposalConfig,
    directory: Path,
    gateway: LlmGateway,
) -> tuple[PartialObservation, RequestTiming]:
    # Distinct executions preserve earlier failed attempts on resume, without votes.
    executions = directory / "executions"
    executions.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="execution-", dir=executions))
    recorder = _RecordingGateway(gateway, staging)
    measured = MeasuredLlmGateway(recorder)
    (directory / "response.json").unlink(missing_ok=True)
    value = {}
    provided_fields = ()
    response_sha256 = None
    error = None
    try:
        result = generate_with_retry(
            measured,
            prepared.request,
            attempts=config.retry_attempts,
            backoff_seconds=config.retry_backoff_seconds,
            retry_timeouts=config.retry_timeouts,
            truncation_retry_max_tokens=config.truncation_retry_max_tokens,
            retry_on_truncation=config.retry_on_truncation,
        )
        response = asdict(result)
        _atomic_json(directory / "response.json", response)
        response_sha256 = structure_fingerprint(response)
        provided_fields = tuple(sorted(result.value))
        if result.model != config.model or result.prompt_version != config.prompt_version:
            raise ValueError("provider response model or prompt identity differs from request")
        value = validate_partial_response(
            result.value, prepared.request.output_schema, prepared.plan
        )
        outcome = "evaluated"
    except Exception as exc:  # Isolate per-clause model/schema failures, not bad inputs.
        outcome, value = "failed", {}
        error = f"{type(exc).__name__}: {exc}"
    observation = PartialObservation(
        plan=prepared.plan,
        request_fingerprint=prepared.fingerprint,
        provider=config.provider,
        model=config.model,
        outcome=outcome,
        states=observation_states(prepared.plan, outcome),
        values=value,
        provided_fields=provided_fields,
        response_sha256=response_sha256,
        error=error,
    )
    _atomic_json(staging / "request-timing.json", measured.timing.model_dump(mode="json"))
    _atomic_json(staging / "partial-observation.json", observation.model_dump(mode="json"))
    _atomic_json(directory / "partial-observation.json", observation.model_dump(mode="json"))
    return observation, measured.timing


def run_partial_proposals(
    config: PartialProposalConfig,
    *,
    resources: Path,
    output_directory: Path,
    examples: tuple[EvaluationExample, ...],
    source_fingerprints: dict[str, str] | None = None,
    execute: bool = False,
    gateway_factory: Callable[[], LlmGateway] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Plan by default; execute only explicit requests. The gateway is created lazily.

    The output identity is immutable. Changed rules, context, attributes, prompts
    or generation settings require another output directory, never stale reuse.
    Existing complete proposals are intentionally neither searched nor imported.
    """
    task_resources = PartialTaskResources.load(resources, config)
    eligibility_policy = SemanticTaskEligibilityPolicy.from_task(task_resources.task)
    if not examples or len({e.id for e in examples}) != len(examples):
        raise ValueError("partial input selection must be nonempty with unique example ids")
    if any(not isinstance(e.id, str) or not e.id.strip() for e in examples):
        raise ValueError("example ids must be nonempty strings")
    if config.include_example_ids is not None:
        if set(config.include_example_ids) - {e.id for e in examples}:
            raise ValueError("selected example ids are missing from dataset")
        selected = tuple(e for e in examples if e.id in config.include_example_ids)
    else:
        selected = examples
    if config.limit is not None:
        selected = selected[: config.limit]
    if not selected:
        raise ValueError("partial selection is empty")
    prepared = tuple(
        prepare_partial_request(config, e.id, e.input, task_resources) for e in selected
    )
    if len({p.plan.clause.key for p in prepared}) != len(prepared):
        raise ValueError("duplicate clause identity in partial dataset")
    eligibility = {
        e.id: eligibility_from_input(eligibility_policy, dict(e.input)) for e in selected
    }
    manifest = {
        "schema_version": "1.0",
        "kind": "partial-run-plan",
        "experimental_only": True,
        "config": config.model_dump(mode="json"),
        "source_fingerprints": source_fingerprints or {},
        "input_count": len(examples),
        "cases": [
            {
                "example_id": p.example_id,
                "fingerprint": p.fingerprint,
                "eligibility": eligibility[p.example_id].model_dump(mode="json"),
            }
            for p in prepared
        ],
    }
    root = output_directory.resolve()
    if any(
        root.is_relative_to(Path(name).resolve())
        for name in (
            "data",
            "src/standards_atlas/resources",
            ".atlas/data/documents",
            ".atlas/data/knowledge-evidence",
        )
    ):
        raise ValueError("partial output must not be a canonical or public data directory")
    manifest_path = root / "partial-run-plan.json"
    existed = root.exists()
    if existed and not manifest_path.is_file():
        raise ValueError(
            "partial output exists without a matching run plan; choose a new directory"
        )
    root.mkdir(parents=True, exist_ok=True)
    with _run_lock(root):
        if manifest_path.is_file():
            stored = _read_json(manifest_path)
            require_supported_schema("partial-proposal-run", stored.get("schema_version"))
            if stored != manifest:
                raise ValueError(
                    "partial run input identity changed; choose a new output directory"
                )
        else:
            _atomic_json(manifest_path, manifest)
        cases: dict[str, dict[str, Any]] = {}
        directories: dict[str, Path] = {}
        pending = []
        reused = 0
        for item in prepared:
            directory = root / "cases" / structure_fingerprint({"example_id": item.example_id})
            if not directory.resolve().is_relative_to(root):
                raise ValueError("partial case directory escapes the output")
            directory.mkdir(parents=True, exist_ok=True)
            directories[item.example_id] = directory
            plan_path = directory / "partial-request-plan.json"
            plan_payload = item.plan.model_dump(mode="json")
            if plan_path.is_file():
                stored_plan = _read_json(plan_path)
                require_supported_schema("partial-request-plan", stored_plan.get("schema_version"))
                if stored_plan != plan_payload:
                    raise ValueError("stored partial plan differs from its source-bound identity")
            _atomic_json(plan_path, plan_payload)
            _atomic_json(
                directory / "eligibility.json", eligibility[item.example_id].model_dump(mode="json")
            )
            if item.request is not None:
                request_path = directory / "request.json"
                if request_path.is_file():
                    stored_request = _read_json(request_path)
                    if (
                        stored_request.get("metadata", {}).get("qualification_input_fingerprint")
                        != item.fingerprint
                    ):
                        raise ValueError("stored partial request fingerprint mismatch")
                    if stored_request.get("output_schema") != dict(item.request.output_schema):
                        raise ValueError("stored partial request schema mismatch")
                _atomic_json(request_path, serialize_generation_request(item.request))
            case = {
                "example_id": item.example_id,
                "clause": item.plan.clause.model_dump(mode="json"),
                "requested_attributes": list(item.plan.requested_attributes),
                "fixed_attributes": dict(item.plan.fixed_attributes),
                "case_directory": directory.relative_to(root).as_posix(),
                "status": "planned",
                "reused": False,
            }
            cases[item.example_id] = case
            if not eligibility[item.example_id].eligible:
                case["status"] = "ineligible"
                continue
            observation = _resume_observation(directory, item, config)
            if observation is not None:
                reused += int(observation.outcome == "evaluated")
                case.update(status=observation.outcome, reused=True)
            elif item.request is None:
                observation = PartialObservation(
                    plan=item.plan,
                    request_fingerprint=item.fingerprint,
                    provider=config.provider,
                    model=config.model,
                    outcome="not_requested",
                    states=observation_states(item.plan, "not_requested"),
                )
                _atomic_json(
                    directory / "partial-observation.json", observation.model_dump(mode="json")
                )
                case["status"] = "not_requested"
            elif execute:
                pending.append(item)
        gateway = None

        def process(current, total, item):
            nonlocal gateway
            if gateway is None:
                if gateway_factory is None:
                    raise ValueError("execution of pending questions requires a gateway factory")
                gateway = gateway_factory()
            if progress:
                progress(
                    f"[{current}/{total}] {item.example_id}: "
                    f"{len(item.plan.requested_attributes)} requested attributes"
                )
            observation, timing = _execute_case(item, config, directories[item.example_id], gateway)
            cases[item.example_id]["status"] = observation.outcome
            if observation.error:
                cases[item.example_id]["error"] = observation.error
            return ProposalItemOutcome(
                generated=observation.outcome == "evaluated",
                error=observation.error,
                fresh_predictions=timing.fresh_response_count,
                cached_predictions=timing.cached_response_count,
                fresh_inference_duration_seconds=timing.fresh_inference_duration_seconds or 0.0,
                request_timing=timing,
            )

        batch = ProposalBatchExecutor().execute(pending, process)
        timing = batch.request_timing or RequestTiming()
        counts = Counter(item["status"] for item in cases.values())
        report = {
            "schema_version": "1.0",
            "kind": "partial-run-report",
            "experimental_only": True,
            "executed": execute,
            "input_count": len(examples),
            "selected_count": len(prepared),
            "accounted_count": len(cases),
            "status_counts": dict(counts),
            "planned_request_count": sum(
                p.plan.request_count for p in prepared if eligibility[p.example_id].eligible
            ),
            "new_observation_count": batch.generated,
            "failed_observation_count": batch.failed,
            "reused_observation_count": reused,
            "request_timing": timing.model_dump(mode="json"),
            "request_timing_scope": "current invocation; prior execution files are retained",
            "logical_model_observation_count": counts["evaluated"],
            "production_early_exit_count": None,
            "production_note": "Experimental task only; no consensus, routing or publication.",
            "cases": list(cases.values()),
        }
        _atomic_json(root / "partial-run-report.json", report)
        return report
