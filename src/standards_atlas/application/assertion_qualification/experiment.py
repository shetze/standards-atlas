"""AP03 bounded experiment planning, execution, resume and stage-aware reporting."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from functools import partial
from typing import ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.assertion_qualification.evaluation import (
    AssertionQualificationEvaluator,
    golden_suite_sha256,
)
from standards_atlas.application.assertion_qualification.models import (
    AssertionGoldenSuite,
    AssertionQualificationReport,
)
from standards_atlas.application.context.input_binding import ContextSourcePackage
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.evaluation.source_bound_prompt import semantic_prompt_repository
from standards_atlas.application.knowledge_proposal_extraction import (
    KnowledgeProposalExtractionService,
    ProposalExtractionContext,
    assertion_context_source_package,
    assertion_interpretation_context,
)
from standards_atlas.application.knowledge_proposal_extraction.pipeline import (
    prepare_knowledge_proposal_request,
)
from standards_atlas.application.ports.knowledge_proposals import KnowledgeProposalExtractor
from standards_atlas.application.ports.llm_gateway import (
    LlmContextWindowError,
    LlmGateway,
    LlmGatewayError,
    LlmHealth,
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.domain.model import (
    ClauseApplicability,
    ContextSourcePackageBinding,
    DocumentKnowledgeProposal,
    EngineeringDocument,
)

AP03_EXPERIMENT_CONTRACT = "ap03-bounded-assertion-experiment-v1"
AP03_EXPERIMENT_REPORT_CONTRACT = "ap03-stage-aware-comparison-v1"
ASSERTION_EXPERIMENT_MANIFEST_SCHEMA_VERSION = 1
ASSERTION_EXPERIMENT_STATE_SCHEMA_VERSION = 1
ASSERTION_EXPERIMENT_REPORT_SCHEMA_VERSION = 1


class ExperimentOperation(StrEnum):
    PLAN = "plan"
    RUN = "run"
    RESUME = "resume"
    CACHE_REPLAY = "cache_replay"


class ExperimentAttemptStatus(StrEnum):
    OK = "ok"
    TIMEOUT = "timeout"
    CONTEXT_LIMIT = "context_limit"
    RESPONSE_ERROR = "response_error"
    UNAVAILABLE = "unavailable"
    VALIDATION_ERROR = "validation_error"
    BUDGET_BLOCKED = "budget_blocked"
    OUTCOME_UNKNOWN = "outcome_unknown"
    CACHE_REPLAY_REJECTED = "cache_replay_rejected"


class ExperimentBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_calls: int = Field(ge=0)
    max_retries_per_case: int = Field(default=0, ge=0)
    max_total_tokens: int | None = Field(default=None, ge=1)
    max_runtime_seconds: float | None = Field(default=None, gt=0)


class ExperimentCaseBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    source_package_binding: ContextSourcePackageBinding
    rendered_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def source_package_sha256(self) -> str:
        return self.source_package_binding.package_sha256


class AssertionExperimentManifest(SchemaBoundModel):
    """Bound experiment identity. Planning this object performs no inference."""

    SCHEMA_FAMILY: ClassVar[str] = "assertion-experiment-manifest"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_EXPERIMENT_MANIFEST_SCHEMA_VERSION
    contract_id: str = AP03_EXPERIMENT_CONTRACT
    experiment_id: str = Field(min_length=1)
    plan_revision: str = Field(default="1.0.0", min_length=1)
    creation_provenance: str = Field(default="standards-atlas-ap03-series-c", min_length=1)
    code_revision: str = Field(min_length=1)
    variant_id: str = Field(min_length=1)
    partition: str = Field(min_length=1)
    golden_suite_id: str = Field(min_length=1)
    golden_suite_version: str = Field(min_length=1)
    golden_suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ontology_versions: tuple[str, ...]
    prompt_version: str = Field(min_length=1)
    task_schema_version: str = Field(default="1.0.0", min_length=1)
    data_route: str = Field(default="local-private-context-source-packages", min_length=1)
    privacy_classification: str = Field(default="protected", min_length=1)
    execution_authorized: bool = False
    authorization_reference: str | None = None
    model_route: str = Field(min_length=1)
    runtime_config_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    requested_model: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int | None = None
    max_output_tokens_per_call: int | None = Field(default=None, ge=1)
    reasoning_enabled: bool | None = None
    repetitions: int = Field(default=1, ge=1)
    bypass_cache_for_repetitions: bool = True
    enabled_call_kinds: tuple[str, ...] = ("extractor",)
    conservative_call_upper_bound: int = Field(ge=1)
    cases: tuple[ExperimentCaseBinding, ...] = Field(min_length=1)
    budget: ExperimentBudget

    @model_validator(mode="after")
    def call_budget_covers_no_more_than_declared_bound(self) -> AssertionExperimentManifest:
        if len({(case.document_key, case.clause_id) for case in self.cases}) != len(self.cases):
            raise ValueError("experiment cases must be unique by document/clause")
        if self.execution_authorized and not self.authorization_reference:
            raise ValueError("authorized experiment plans require authorization_reference")
        if not self.execution_authorized and self.authorization_reference is not None:
            raise ValueError("authorization_reference requires execution_authorized=true")
        if self.enabled_call_kinds != ("extractor",):
            raise ValueError(
                "Series-C experiment runner supports only the existing extractor call kind"
            )
        expected_upper = len(self.cases) * self.repetitions * (1 + self.budget.max_retries_per_case)
        if self.conservative_call_upper_bound != expected_upper:
            raise ValueError(
                "conservative_call_upper_bound does not match cases/repetitions/retries"
            )
        minimum = len(self.cases) * self.repetitions
        if self.budget.max_calls < minimum:
            raise ValueError(
                "experiment max_calls is below the required one-call-per-case/repetition bound"
            )
        return self


class ExperimentUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ExperimentAttemptRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt_id: str = Field(pattern=r"^attempt-[0-9a-f]{24}$")
    repetition: int = Field(ge=1)
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    operation: ExperimentOperation
    status: ExperimentAttemptStatus
    source_package_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    prompt_version: str | None = None
    requested_model: str | None = None
    effective_model: str | None = None
    provider: str | None = None
    temperature: float | None = None
    seed: int | None = None
    max_tokens: int | None = None
    reasoning_enabled: bool | None = None
    input_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    raw_response_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    duration_ms: int | None = Field(default=None, ge=0)
    usage: ExperimentUsage | None = None
    cached: bool | None = None
    error_type: str | None = None
    message: str | None = None
    failure_stage: str | None = None
    private_raw_artifact: str | None = None
    proposal_run_id: str | None = None


class AssertionExperimentState(SchemaBoundModel):
    SCHEMA_FAMILY: ClassVar[str] = "assertion-experiment-state"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_EXPERIMENT_STATE_SCHEMA_VERSION
    contract_id: str = AP03_EXPERIMENT_CONTRACT
    experiment_id: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempts: tuple[ExperimentAttemptRecord, ...] = ()
    completed_cells: tuple[str, ...] = ()
    blocked_reason: str | None = None


class ExperimentCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selected_cases: int
    planned_cells: int
    attempted_cells: int
    technically_completed_cells: int
    failed_cells: int
    not_executed_cells: int


class ExperimentEffort(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    calls: int
    cached_calls: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    duration_ms: int | None
    monetary_cost: None = None


class AssertionExperimentReport(SchemaBoundModel):
    """Text-safe comparison wrapper around the existing evaluator report."""

    SCHEMA_FAMILY: ClassVar[str] = "assertion-experiment-report"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = ASSERTION_EXPERIMENT_REPORT_SCHEMA_VERSION
    contract_id: str = AP03_EXPERIMENT_REPORT_CONTRACT
    experiment_id: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    variant_id: str
    coverage: ExperimentCoverage
    stage_failures: Mapping[str, int]
    effort: ExperimentEffort
    qualification_report: AssertionQualificationReport
    baseline_qualification_report: AssertionQualificationReport | None = None
    evaluation_repetition: int = Field(default=1, ge=1)
    review_questions: tuple[str, ...] = ()
    open_diagnostics: tuple[str, ...] = ()


class ExperimentRepository(Protocol):
    def save_manifest(self, manifest: AssertionExperimentManifest) -> str: ...
    def load_manifest(self, experiment_id: str) -> AssertionExperimentManifest: ...
    def save_state(self, state: AssertionExperimentState) -> None: ...
    def load_state(self, experiment_id: str) -> AssertionExperimentState | None: ...
    def save_private_attempt(self, attempt_id: str, payload: Mapping[str, object]) -> str: ...
    def save_proposal(self, proposal: DocumentKnowledgeProposal) -> None: ...
    def load_proposal(
        self, proposal_run_id: str, document_key: str
    ) -> DocumentKnowledgeProposal | None: ...


class SourcePackageRepository(Protocol):
    def save(self, package: ContextSourcePackage): ...
    def load(self, binding): ...


class BudgetExceeded(LlmGatewayError):
    pass


class ExperimentBindingError(LlmGatewayError):
    pass


def manifest_sha256(manifest: AssertionExperimentManifest) -> str:
    payload = manifest.model_dump(mode="json")
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def plan_assertion_experiment(
    suite: AssertionGoldenSuite,
    documents: Mapping[str, EngineeringDocument],
    *,
    experiment_id: str,
    code_revision: str,
    variant_id: str,
    prompt_version: str,
    task_schema_version: str = "1.0.0",
    model_route: str,
    source_packages: SourcePackageRepository,
    budget: ExperimentBudget,
    requested_model: str | None = None,
    runtime_config_sha256: str | None = None,
    temperature: float = 0.0,
    seed: int | None = None,
    max_output_tokens_per_call: int | None = None,
    reasoning_enabled: bool | None = None,
    repetitions: int = 1,
    execution_authorized: bool = False,
    authorization_reference: str | None = None,
    prompt_repository: PromptRepository | None = None,
) -> AssertionExperimentManifest:
    bindings: list[ExperimentCaseBinding] = []
    for case in suite.cases:
        document = documents.get(case.source_document_key)
        if document is None:
            raise ValueError(f"missing EngineeringDocument for {case.source_document_key!r}")
        clause = _clause_by_id(document, case.clause_id.value)
        package = assertion_context_source_package(document, clause)
        binding = source_packages.save(package)
        prepared = prepare_knowledge_proposal_request(
            clause,
            document_key=document.key.value,
            ontology_versions=suite.ontology_versions,
            source_package=package,
            interpretation_context=assertion_interpretation_context(
                document, clause, applicability=ClauseApplicability()
            ),
            prompt_repository=prompt_repository or semantic_prompt_repository(),
            prompt_version=prompt_version,
            task_schema_version=task_schema_version,
            model=requested_model,
            temperature=temperature,
            seed=seed,
            max_tokens=max_output_tokens_per_call,
            reasoning_enabled=reasoning_enabled,
            metadata=(
                {"use_cache": False}
                if temperature != 0.0
                or seed is not None
                or max_output_tokens_per_call is not None
                or reasoning_enabled is not None
                else None
            ),
        )
        bindings.append(
            ExperimentCaseBinding(
                document_key=case.source_document_key,
                clause_id=case.clause_id.value,
                source_package_binding=binding,
                rendered_request_sha256=_request_sha256(prepared.generation_request),
            )
        )
    return AssertionExperimentManifest(
        experiment_id=experiment_id,
        code_revision=code_revision,
        variant_id=variant_id,
        partition=suite.partition.value,
        golden_suite_id=suite.id,
        golden_suite_version=suite.version,
        golden_suite_sha256=golden_suite_sha256(suite),
        ontology_versions=suite.ontology_versions,
        prompt_version=prompt_version,
        task_schema_version=task_schema_version,
        model_route=model_route,
        execution_authorized=execution_authorized,
        authorization_reference=authorization_reference,
        requested_model=requested_model,
        runtime_config_sha256=runtime_config_sha256,
        temperature=temperature,
        seed=seed,
        max_output_tokens_per_call=max_output_tokens_per_call,
        reasoning_enabled=reasoning_enabled,
        repetitions=repetitions,
        conservative_call_upper_bound=(
            len(bindings) * repetitions * (1 + budget.max_retries_per_case)
        ),
        cases=tuple(bindings),
        budget=budget,
    )


class _BudgetLedger:
    def __init__(
        self, manifest: AssertionExperimentManifest, state: AssertionExperimentState
    ) -> None:
        self.manifest = manifest
        self.calls = sum(
            a.status is not ExperimentAttemptStatus.BUDGET_BLOCKED for a in state.attempts
        )
        self.tokens = sum(
            a.usage.total_tokens for a in state.attempts if a.usage and a.usage.total_tokens
        )
        self.duration_ms = sum(a.duration_ms or 0 for a in state.attempts)

    def before_call(self, request: StructuredGenerationRequest) -> None:
        if self.calls >= self.manifest.budget.max_calls:
            raise BudgetExceeded("max_calls exhausted before inference")
        if (
            self.manifest.budget.max_runtime_seconds is not None
            and self.duration_ms >= self.manifest.budget.max_runtime_seconds * 1000
        ):
            raise BudgetExceeded("max_runtime_seconds exhausted before inference")
        if self.manifest.budget.max_total_tokens is not None:
            if self.tokens >= self.manifest.budget.max_total_tokens:
                raise BudgetExceeded("max_total_tokens exhausted before inference")
            if (
                request.max_tokens is not None
                and self.tokens + request.max_tokens > self.manifest.budget.max_total_tokens
            ):
                raise BudgetExceeded("remaining token budget is below requested max_tokens")
        self.calls += 1

    def after_duration(self, duration_ms: int) -> None:
        self.duration_ms += duration_ms

    def after_error(self, duration_ms: int, usage: ExperimentUsage | None) -> None:
        self.duration_ms += duration_ms
        if usage and usage.total_tokens is not None:
            self.tokens += usage.total_tokens

    def after_call(self, result: StructuredGenerationResult) -> None:
        self.duration_ms += result.duration_ms
        if result.usage and result.usage.total_tokens is not None:
            self.tokens += result.usage.total_tokens


def _persist_started_record(
    record: ExperimentAttemptRecord,
    *,
    started_records: list[ExperimentAttemptRecord],
    records: list[ExperimentAttemptRecord],
    persist: Callable[[], None],
) -> None:
    started_records.append(record)
    records.append(record)
    persist()


class _AttemptGateway:
    def __init__(
        self,
        delegate: LlmGateway,
        *,
        repository: ExperimentRepository,
        budget: _BudgetLedger,
        attempt_id: str,
        operation: ExperimentOperation,
        base_record: dict[str, object],
        expected_request_sha256: str,
        on_record: Callable[[ExperimentAttemptRecord], None],
        on_started: Callable[[ExperimentAttemptRecord], None] | None = None,
        reject_cached: bool = True,
    ) -> None:
        self._delegate = delegate
        self._repository = repository
        self._budget = budget
        self._attempt_id = attempt_id
        self._operation = operation
        self._base_record = base_record
        self._expected_request_sha256 = expected_request_sha256
        self._on_record = on_record
        self._on_started = on_started
        self._reject_cached = reject_cached
        self.called = False

    def health(self) -> LlmHealth:
        return self._delegate.health()

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        if self.called:
            raise RuntimeError("one AP03 attempt may issue at most one extractor gateway call")
        self.called = True
        request_payload = _request_payload(request)
        actual_request_sha256 = _request_sha256(request)
        if actual_request_sha256 != self._expected_request_sha256:
            error = ExperimentBindingError(
                "rendered request differs from the approved experiment plan"
            )
            private = self._repository.save_private_attempt(
                self._attempt_id,
                {
                    "request": request_payload,
                    "binding_error": {
                        "expected_request_sha256": self._expected_request_sha256,
                        "actual_request_sha256": actual_request_sha256,
                    },
                },
            )
            self._emit(
                request,
                ExperimentAttemptStatus.VALIDATION_ERROR,
                error=error,
                private_raw_artifact=private,
                failure_stage="binding",
            )
            raise error
        try:
            self._budget.before_call(request)
        except BudgetExceeded as error:
            self._emit(
                request,
                ExperimentAttemptStatus.BUDGET_BLOCKED,
                error=error,
                failure_stage="budget",
            )
            raise
        if self._on_started is not None:
            self._on_started(
                self._record(
                    request,
                    ExperimentAttemptStatus.OUTCOME_UNKNOWN,
                    error_type="InferenceInProgress",
                    message="inference outcome is unknown until the gateway call completes",
                    failure_stage="inference",
                )
            )
        started = time.monotonic()
        try:
            result = self._delegate.generate_structured(request)
        except LlmGatewayError as error:
            duration_ms = round((time.monotonic() - started) * 1000)
            error_usage = _gateway_error_usage(error)
            self._budget.after_error(duration_ms, error_usage)
            private = self._repository.save_private_attempt(
                self._attempt_id,
                {"request": request_payload, "error": _error_raw_payload(error)},
            )
            self._emit(
                request,
                _gateway_error_status(error),
                error=error,
                duration_ms=duration_ms,
                reported_usage=error_usage,
                private_raw_artifact=private,
                failure_stage=_gateway_failure_stage(error),
            )
            raise
        self._budget.after_call(result)
        private = self._repository.save_private_attempt(
            self._attempt_id,
            {"request": request_payload, "raw_response": result.raw_response},
        )
        if result.cached and self._reject_cached:
            error = LlmResponseError("cached result cannot satisfy a fresh AP03 inference attempt")
            self._emit(
                request,
                ExperimentAttemptStatus.CACHE_REPLAY_REJECTED,
                result=result,
                error=error,
                private_raw_artifact=private,
                failure_stage="cache",
            )
            raise error
        self._emit(
            request,
            ExperimentAttemptStatus.OK,
            result=result,
            private_raw_artifact=private,
        )
        return result

    def _record(
        self,
        request: StructuredGenerationRequest,
        status: ExperimentAttemptStatus,
        *,
        result: StructuredGenerationResult | None = None,
        error: Exception | None = None,
        error_type: str | None = None,
        message: str | None = None,
        duration_ms: int | None = None,
        reported_usage: ExperimentUsage | None = None,
        private_raw_artifact: str | None = None,
        failure_stage: str | None = None,
    ) -> ExperimentAttemptRecord:
        usage = reported_usage
        if result and result.usage:
            usage = ExperimentUsage(
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                total_tokens=result.usage.total_tokens,
            )
        return ExperimentAttemptRecord(
            **self._base_record,
            attempt_id=self._attempt_id,
            operation=self._operation,
            status=status,
            prompt_version=request.prompt_version,
            requested_model=request.model,
            effective_model=result.model if result else None,
            provider=result.provider if result else None,
            temperature=request.temperature,
            seed=request.seed,
            max_tokens=request.max_tokens,
            reasoning_enabled=request.reasoning_enabled,
            input_hash=result.input_hash if result else None,
            raw_response_hash=result.raw_response_hash if result else None,
            duration_ms=result.duration_ms if result else duration_ms,
            usage=usage,
            cached=result.cached if result else None,
            error_type=error_type or (type(error).__name__ if error else None),
            message=(
                message
                if message is not None
                else (_public_error_message(error) if error else None)
            ),
            failure_stage=failure_stage,
            private_raw_artifact=private_raw_artifact,
        )

    def _emit(
        self,
        request: StructuredGenerationRequest,
        status: ExperimentAttemptStatus,
        **kwargs,
    ) -> None:
        self._on_record(self._record(request, status, **kwargs))


ExtractorFactory = Callable[[LlmGateway, AssertionExperimentManifest], KnowledgeProposalExtractor]


class AssertionExperimentService:
    """Execute one approved manifest sequentially through existing extraction components."""

    def __init__(
        self,
        *,
        repository: ExperimentRepository,
        source_packages: SourcePackageRepository,
        gateway: LlmGateway,
        extractor_factory: ExtractorFactory,
    ) -> None:
        self._repository = repository
        self._source_packages = source_packages
        self._gateway = gateway
        self._extractor_factory = extractor_factory

    def run(
        self,
        manifest: AssertionExperimentManifest,
        suite: AssertionGoldenSuite,
        documents: Mapping[str, EngineeringDocument],
        *,
        resume: bool = False,
    ) -> AssertionExperimentState:
        if not manifest.execution_authorized:
            raise ExperimentBindingError(
                "experiment execution is not authorized; bind an explicitly authorized plan"
            )
        _validate_manifest_suite(manifest, suite)
        digest = manifest_sha256(manifest)
        previous = self._repository.load_state(manifest.experiment_id)
        if previous is not None and not resume:
            raise ValueError("experiment state already exists; use resume instead of run")
        state = previous or AssertionExperimentState(
            experiment_id=manifest.experiment_id,
            manifest_sha256=digest,
        )
        if state.manifest_sha256 != digest:
            raise ValueError("experiment manifest changed; existing attempts cannot be reused")
        records = list(state.attempts)
        completed = set(state.completed_cells)
        budget = _BudgetLedger(manifest, state)
        operation = ExperimentOperation.RESUME if resume else ExperimentOperation.RUN

        for repetition in range(1, manifest.repetitions + 1):
            for case in manifest.cases:
                cell = _cell_id(repetition, case.document_key, case.clause_id)
                if cell in completed:
                    continue
                document = documents.get(case.document_key)
                if document is None:
                    raise ValueError(f"missing EngineeringDocument for {case.document_key!r}")
                _clause_by_id(document, case.clause_id)
                binding = case.source_package_binding
                package = self._source_packages.load(binding)
                if package is None:
                    raise ValueError(
                        f"source package is unavailable for {case.document_key}:{case.clause_id}"
                    )
                prior_attempts = sum(
                    item.repetition == repetition
                    and item.document_key == case.document_key
                    and item.clause_id == case.clause_id
                    and item.status is not ExperimentAttemptStatus.BUDGET_BLOCKED
                    for item in records
                )
                allowed_attempts = 1 + manifest.budget.max_retries_per_case
                if prior_attempts >= allowed_attempts:
                    return self._blocked(
                        manifest,
                        digest,
                        records,
                        completed,
                        "technical retry limit exhausted with an unresolved prior attempt",
                    )
                for technical_retry in range(prior_attempts, allowed_attempts):
                    attempt_number = 1 + sum(
                        item.repetition == repetition
                        and item.document_key == case.document_key
                        and item.clause_id == case.clause_id
                        for item in records
                    )
                    attempt_id = _attempt_id(
                        digest, repetition, case.document_key, case.clause_id, attempt_number
                    )
                    emitted: list[ExperimentAttemptRecord] = []
                    started_records: list[ExperimentAttemptRecord] = []

                    persist_started = partial(
                        _persist_started_record,
                        started_records=started_records,
                        records=records,
                        persist=partial(
                            self._persist_intermediate,
                            manifest,
                            digest,
                            records,
                            completed,
                        ),
                    )

                    gateway = _AttemptGateway(
                        self._gateway,
                        repository=self._repository,
                        budget=budget,
                        attempt_id=attempt_id,
                        operation=operation,
                        base_record={
                            "repetition": repetition,
                            "document_key": case.document_key,
                            "clause_id": case.clause_id,
                            "attempt_number": attempt_number,
                            "source_package_sha256": case.source_package_sha256,
                        },
                        expected_request_sha256=case.rendered_request_sha256,
                        on_record=emitted.append,
                        on_started=persist_started,
                        reject_cached=manifest.bypass_cache_for_repetitions,
                    )
                    extractor = self._extractor_factory(gateway, manifest)
                    proposal_run_id = (
                        f"{manifest.experiment_id}-r{repetition}-{case.clause_id}-a{attempt_number}"
                    )
                    proposal = KnowledgeProposalExtractionService(extractor).extract_document(
                        document,
                        proposal_run_id=proposal_run_id,
                        ontology_versions=manifest.ontology_versions,
                        clause_ids=frozenset({case.clause_id}),
                        context_by_clause={
                            case.clause_id: ProposalExtractionContext(source_package=package)
                        },
                    )
                    if not emitted:
                        raise RuntimeError("extractor did not issue the expected gateway call")
                    record = emitted[0].model_copy(update={"proposal_run_id": proposal_run_id})
                    if record.status is ExperimentAttemptStatus.OK and proposal.failures:
                        failure = proposal.failures[0]
                        private_path = self._repository.save_private_attempt(
                            record.attempt_id,
                            {
                                "post_gateway_validation_error": {
                                    "error_type": failure.error_type,
                                    "message": failure.message,
                                }
                            },
                        )
                        record = record.model_copy(
                            update={
                                "status": ExperimentAttemptStatus.VALIDATION_ERROR,
                                "error_type": failure.error_type,
                                "message": "productive parser or candidate validation failed",
                                "failure_stage": "productive_parser_or_validation",
                                "private_raw_artifact": private_path,
                            }
                        )
                    if started_records:
                        for index in range(len(records) - 1, -1, -1):
                            if records[index].attempt_id == record.attempt_id:
                                records[index] = record
                                break
                        else:
                            raise RuntimeError("persisted in-progress attempt disappeared")
                    else:
                        records.append(record)
                    self._persist_intermediate(manifest, digest, records, completed)
                    if record.status is ExperimentAttemptStatus.OK:
                        self._repository.save_proposal(proposal)  # type: ignore[attr-defined]
                        completed.add(cell)
                        self._persist_intermediate(manifest, digest, records, completed)
                        break
                    if record.status is ExperimentAttemptStatus.BUDGET_BLOCKED:
                        return self._blocked(manifest, digest, records, completed, record.message)
                    if (
                        not _retryable(record.status)
                        or technical_retry >= manifest.budget.max_retries_per_case
                    ):
                        completed.add(cell)
                        self._persist_intermediate(manifest, digest, records, completed)
                        break
        return AssertionExperimentState(
            experiment_id=manifest.experiment_id,
            manifest_sha256=digest,
            attempts=tuple(records),
            completed_cells=tuple(sorted(completed)),
        )

    def _persist_intermediate(self, manifest, digest, records, completed) -> None:
        self._repository.save_state(
            AssertionExperimentState(
                experiment_id=manifest.experiment_id,
                manifest_sha256=digest,
                attempts=tuple(records),
                completed_cells=tuple(sorted(completed)),
            )
        )

    def _blocked(self, manifest, digest, records, completed, reason) -> AssertionExperimentState:
        state = AssertionExperimentState(
            experiment_id=manifest.experiment_id,
            manifest_sha256=digest,
            attempts=tuple(records),
            completed_cells=tuple(sorted(completed)),
            blocked_reason=reason or "budget exhausted",
        )
        self._repository.save_state(state)
        return state


def evaluate_assertion_experiment(
    manifest: AssertionExperimentManifest,
    state: AssertionExperimentState,
    suite: AssertionGoldenSuite,
    *,
    proposals: Sequence[DocumentKnowledgeProposal],
    source_packages: Sequence[ContextSourcePackage],
    baseline_report: AssertionQualificationReport | None = None,
    evaluation_repetition: int = 1,
) -> AssertionExperimentReport:
    """Use the existing evaluator once, then add only execution/coverage observations."""
    _validate_manifest_suite(manifest, suite)
    if state.manifest_sha256 != manifest_sha256(manifest):
        raise ValueError("experiment state is not bound to this manifest")
    report = AssertionQualificationEvaluator().evaluate(
        suite,
        proposals,
        source_packages=source_packages if proposals else None,
    )
    planned = len(manifest.cases) * manifest.repetitions
    attempted_cells = {
        _cell_id(a.repetition, a.document_key, a.clause_id)
        for a in state.attempts
        if a.status is not ExperimentAttemptStatus.BUDGET_BLOCKED
    }
    ok_cells = {
        _cell_id(a.repetition, a.document_key, a.clause_id)
        for a in state.attempts
        if a.status is ExperimentAttemptStatus.OK
    }
    failed_cells = set(state.completed_cells) - ok_cells
    failures: dict[str, int] = {}
    for attempt in state.attempts:
        if attempt.status is ExperimentAttemptStatus.OK:
            continue
        key = f"{attempt.failure_stage or 'unknown'}:{attempt.status.value}"
        failures[key] = failures.get(key, 0) + 1
    for proposal in proposals:
        for violation in proposal.violations:
            key = f"candidate_rejection:{violation.kind.value}"
            failures[key] = failures.get(key, 0) + 1
    prompt_tokens = _sum_known(a.usage.prompt_tokens if a.usage else None for a in state.attempts)
    completion_tokens = _sum_known(
        a.usage.completion_tokens if a.usage else None for a in state.attempts
    )
    total_tokens = _sum_known(a.usage.total_tokens if a.usage else None for a in state.attempts)
    duration_ms = _sum_known(a.duration_ms for a in state.attempts)
    diagnostics = []
    if state.blocked_reason:
        diagnostics.append(state.blocked_reason)
    review_questions = _review_questions(report)
    if len(ok_cells) < planned:
        diagnostics.append(
            "quality metrics cover only cells with native candidates; "
            "fixed coverage remains reported separately"
        )
    return AssertionExperimentReport(
        experiment_id=manifest.experiment_id,
        manifest_sha256=manifest_sha256(manifest),
        variant_id=manifest.variant_id,
        coverage=ExperimentCoverage(
            selected_cases=len(manifest.cases),
            planned_cells=planned,
            attempted_cells=len(attempted_cells),
            technically_completed_cells=len(ok_cells),
            failed_cells=len(failed_cells),
            not_executed_cells=max(0, planned - len(state.completed_cells)),
        ),
        stage_failures=dict(sorted(failures.items())),
        effort=ExperimentEffort(
            calls=sum(
                a.status is not ExperimentAttemptStatus.BUDGET_BLOCKED for a in state.attempts
            ),
            cached_calls=sum(a.cached is True for a in state.attempts),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
        ),
        qualification_report=report,
        baseline_qualification_report=baseline_report,
        evaluation_repetition=evaluation_repetition,
        review_questions=review_questions,
        open_diagnostics=tuple(diagnostics),
    )


def materialize_experiment_inputs(
    repository: ExperimentRepository,
    source_packages: SourcePackageRepository,
    manifest: AssertionExperimentManifest,
    state: AssertionExperimentState,
    *,
    repetition: int = 1,
) -> tuple[tuple[DocumentKnowledgeProposal, ...], tuple[ContextSourcePackage, ...]]:
    """Rebuild one repetition's clause-local native candidates without choosing best attempts."""
    if repetition < 1 or repetition > manifest.repetitions:
        raise ValueError("evaluation repetition is outside the experiment plan")
    successful: dict[tuple[str, str], ExperimentAttemptRecord] = {}
    for record in state.attempts:
        if record.repetition != repetition or record.status is not ExperimentAttemptStatus.OK:
            continue
        key = (record.document_key, record.clause_id)
        if key in successful:
            raise ValueError("multiple successful attempts exist for one experiment cell")
        successful[key] = record

    by_document: dict[str, list[DocumentKnowledgeProposal]] = {}
    for case in manifest.cases:
        record = successful.get((case.document_key, case.clause_id))
        if record is None or record.proposal_run_id is None:
            continue
        proposal = repository.load_proposal(record.proposal_run_id, case.document_key)
        if proposal is None:
            raise ValueError(f"persisted proposal is missing for attempt {record.attempt_id}")
        by_document.setdefault(case.document_key, []).append(proposal)

    merged = tuple(
        _merge_clause_proposals(manifest, repetition, document_key, proposals)
        for document_key, proposals in sorted(by_document.items())
    )
    packages: list[ContextSourcePackage] = []
    for case in manifest.cases:
        if (case.document_key, case.clause_id) not in successful:
            continue
        package = source_packages.load(case.source_package_binding)
        if package is None:
            raise ValueError(
                f"source package is unavailable for {case.document_key}:{case.clause_id}"
            )
        packages.append(package)
    return merged, tuple(packages)


def _merge_clause_proposals(
    manifest: AssertionExperimentManifest,
    repetition: int,
    document_key: str,
    proposals: Sequence[DocumentKnowledgeProposal],
) -> DocumentKnowledgeProposal:
    if not proposals:
        raise ValueError("cannot merge an empty proposal set")
    if any(item.proposal_provenance != proposals[0].proposal_provenance for item in proposals[1:]):
        raise ValueError("experiment proposal provenance changed within one repetition/document")
    return DocumentKnowledgeProposal(
        proposal_run_id=f"{manifest.experiment_id}-r{repetition}-{document_key}-native",
        source_document_key=document_key,
        ontology_versions=manifest.ontology_versions,
        context_source_bindings=tuple(
            binding for proposal in proposals for binding in proposal.context_source_bindings
        ),
        evidence_anchors=tuple(
            anchor for proposal in proposals for anchor in proposal.evidence_anchors
        ),
        entity_proposals=tuple(
            entity for proposal in proposals for entity in proposal.entity_proposals
        ),
        assertion_proposals=tuple(
            assertion for proposal in proposals for assertion in proposal.assertion_proposals
        ),
        violations=tuple(violation for proposal in proposals for violation in proposal.violations),
        failures=tuple(failure for proposal in proposals for failure in proposal.failures),
        attempts=tuple(attempt for proposal in proposals for attempt in proposal.attempts),
        proposal_provenance=proposals[0].proposal_provenance,
    )


def _review_questions(report: AssertionQualificationReport) -> tuple[str, ...]:
    questions: list[str] = []
    for case in report.cases:
        for finding in case.diagnostic_findings:
            if finding.status.value != "needs_review":
                continue
            codes = ", ".join(code.value for code in finding.codes)
            object_ids = tuple(finding.golden_ids) + tuple(finding.candidate_ids)
            object_part = f"; objects={','.join(object_ids)}" if object_ids else ""
            questions.append(
                f"Review {case.source_document_key}:{case.reference} for {codes}{object_part}."
            )
    return tuple(questions)


def _validate_manifest_suite(
    manifest: AssertionExperimentManifest, suite: AssertionGoldenSuite
) -> None:
    if manifest.golden_suite_sha256 != golden_suite_sha256(suite):
        raise ValueError("experiment manifest golden suite hash does not match supplied suite")
    if manifest.golden_suite_id != suite.id or manifest.golden_suite_version != suite.version:
        raise ValueError("experiment manifest golden suite identity does not match supplied suite")
    if manifest.partition != suite.partition.value:
        raise ValueError("experiment manifest partition does not match supplied suite")
    if manifest.ontology_versions != suite.ontology_versions:
        raise ValueError("experiment manifest ontology versions do not match supplied suite")


def _clause_by_id(document: EngineeringDocument, clause_id: str):
    for clause in document.clauses:
        if clause.id.value == clause_id:
            return clause
    raise ValueError(f"document {document.key.value!r} has no clause {clause_id!r}")


def _request_sha256(request: StructuredGenerationRequest) -> str:
    payload = _request_payload(request)
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _request_payload(request: StructuredGenerationRequest) -> dict[str, object]:
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


def _gateway_error_usage(error: LlmGatewayError) -> ExperimentUsage | None:
    raw_response = getattr(error, "raw_response", None)
    if not isinstance(raw_response, Mapping):
        return None
    raw_usage = raw_response.get("usage")
    if not isinstance(raw_usage, Mapping):
        return None

    prompt_tokens = _usage_int(raw_usage, "prompt_tokens", "input_tokens")
    completion_tokens = _usage_int(raw_usage, "completion_tokens", "output_tokens")
    total_tokens = _usage_int(raw_usage, "total_tokens")
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens
    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        return None
    return ExperimentUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _usage_int(raw_usage: Mapping[object, object], *names: str) -> int | None:
    for name in names:
        value = raw_usage.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _error_raw_payload(error: LlmGatewayError) -> dict[str, object | None]:
    return {
        "error_type": type(error).__name__,
        "message": str(error),
        "raw_content": getattr(error, "raw_content", None),
        "raw_response": getattr(error, "raw_response", None),
        "finish_reason": getattr(error, "finish_reason", None),
    }


def _gateway_error_status(error: LlmGatewayError) -> ExperimentAttemptStatus:
    if isinstance(error, LlmContextWindowError):
        return ExperimentAttemptStatus.CONTEXT_LIMIT
    if isinstance(error, LlmTimeoutError):
        return ExperimentAttemptStatus.TIMEOUT
    if isinstance(error, LlmUnavailableError):
        return ExperimentAttemptStatus.UNAVAILABLE
    if isinstance(error, LlmResponseError):
        return ExperimentAttemptStatus.RESPONSE_ERROR
    return ExperimentAttemptStatus.OUTCOME_UNKNOWN


def _public_error_message(error: Exception | None) -> str | None:
    if error is None:
        return None
    if isinstance(error, BudgetExceeded):
        return str(error)
    if isinstance(error, ExperimentBindingError):
        return "experiment request binding changed"
    if isinstance(error, LlmContextWindowError):
        return "model context limit was exceeded"
    if isinstance(error, LlmTimeoutError):
        return "model request timed out"
    if isinstance(error, LlmUnavailableError):
        return "model endpoint was unavailable"
    if isinstance(error, LlmResponseError):
        return "model response was rejected"
    return "gateway outcome is unknown"


def _gateway_failure_stage(error: LlmGatewayError) -> str:
    if isinstance(error, ExperimentBindingError):
        return "binding"
    if isinstance(error, (LlmTimeoutError, LlmUnavailableError)):
        return "transport"
    if isinstance(error, LlmContextWindowError):
        return "request_context"
    if isinstance(error, LlmResponseError):
        return "gateway_response"
    return "gateway_unknown"


def _retryable(status: ExperimentAttemptStatus) -> bool:
    return status in {ExperimentAttemptStatus.TIMEOUT, ExperimentAttemptStatus.UNAVAILABLE}


def _attempt_id(digest: str, repetition: int, document: str, clause: str, number: int) -> str:
    raw = f"{digest}|{repetition}|{document}|{clause}|{number}".encode()
    return "attempt-" + hashlib.sha256(raw).hexdigest()[:24]


def _cell_id(repetition: int, document: str, clause: str) -> str:
    return f"r{repetition}:{document}:{clause}"


def _sum_known(values) -> int | None:
    items = list(values)
    if not items or any(value is None for value in items):
        return None
    return sum(items)  # type: ignore[arg-type]
