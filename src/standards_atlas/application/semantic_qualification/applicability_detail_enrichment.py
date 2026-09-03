"""Selective applicability-detail enrichment after presence consensus."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.evaluation.models import EvaluationExample, PromptDefinition
from standards_atlas.application.evaluation.schema import validate_schema
from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from standards_atlas.application.semantic_qualification.consensus import ConsensusReport
from standards_atlas.application.semantic_qualification.qualification_coverage import (
    QualificationCoverage,
)
from standards_atlas.application.semantic_qualification.retry import generate_with_retry
from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
)
from standards_atlas.domain.model import ApplicabilityFunction

APPLICABILITY_DETAIL_SELECTION_FILENAME = "applicability-detail-selection.json"
APPLICABILITY_DETAIL_REPORT_FILENAME = "applicability-detail-enrichment.json"
APPLICABILITY_DETAIL_FAILURES_FILENAME = "applicability-detail-failures.json"
APPLICABILITY_DETAIL_ARTIFACT_DIRECTORY = "applicability-detail"


class ApplicabilityDetailEnrichmentConfig(BaseModel):
    """Manifest-owned policy for sparse applicability-detail enrichment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    task: Literal["applicability-detail-enrichment"] = "applicability-detail-enrichment"
    task_version: str = "1.0.0"
    prompt_version: str = "detail-structure-aware-v1"
    model: str | None = None
    max_output_tokens: int = Field(default=512, gt=0)
    truncation_retry_max_tokens: int = Field(default=768, gt=0)
    retry_attempts: int = Field(default=2, ge=1)
    retry_backoff_seconds: float = Field(default=1.0, ge=0.0)
    retry_timeouts: bool = True
    timeout_seconds: float = Field(default=180.0, gt=0.0)

    @model_validator(mode="after")
    def validate_generation_budget(self) -> ApplicabilityDetailEnrichmentConfig:
        if self.truncation_retry_max_tokens < self.max_output_tokens:
            raise ValueError(
                "truncation_retry_max_tokens must not be smaller than max_output_tokens"
            )
        return self


class ApplicabilityDetailOutcome(StrEnum):
    """Operational result of one selected detail-enrichment clause."""

    ENRICHED = "enriched"
    NOT_CONFIRMED = "not_confirmed"
    UNRESOLVED = "unresolved"
    FAILED = "failed"


class ApplicabilityDetailSelectionClause(BaseModel):
    """One final Presence-positive clause selected for detail enrichment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    example_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reference: str | None = None
    heading: str | None = None
    presence_confidence: float = Field(ge=0.0, le=1.0)
    presence_category: str = Field(min_length=1)
    source_requires_review: bool = False
    presence_resolution_source: str = Field(min_length=1)


class ApplicabilityDetailSelection(BaseModel):
    """Deterministic projection of final Presence-positive clauses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    task: Literal["applicability-detail-enrichment"] = "applicability-detail-enrichment"
    task_version: str = Field(min_length=1)
    source_matrix_id: str = Field(min_length=1)
    source_corpus_id: str = Field(min_length=1)
    source_selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_consensus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_coverage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_selected_clause_count: int = Field(ge=0)
    source_qualified_clause_count: int = Field(ge=0)
    source_unqualified_clause_count: int = Field(ge=0)
    source_consensus_clause_count: int = Field(ge=0)
    selected_clause_count: int = Field(ge=0)
    clauses: tuple[ApplicabilityDetailSelectionClause, ...]

    @model_validator(mode="after")
    def validate_selection(self) -> ApplicabilityDetailSelection:
        if self.selected_clause_count != len(self.clauses):
            raise ValueError("selected_clause_count must match clauses")
        if (
            self.source_qualified_clause_count + self.source_unqualified_clause_count
            != self.source_selected_clause_count
        ):
            raise ValueError("source qualification coverage must match source selection")
        if self.source_consensus_clause_count != self.source_qualified_clause_count:
            raise ValueError("source consensus must cover every qualified clause")
        if self.selected_clause_count > self.source_consensus_clause_count:
            raise ValueError("detail selection exceeds final consensus population")
        coordinates = [(item.document_key, item.clause_id) for item in self.clauses]
        if len(coordinates) != len(set(coordinates)):
            raise ValueError("applicability detail selection coordinates must be unique")
        return self

    @property
    def fingerprint(self) -> str:
        return _canonical_sha256(self.model_dump(mode="json"))


class ApplicabilityDetailEvidence(BaseModel):
    """One source span supporting a classified applicability function."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    function: ApplicabilityFunction
    text: str = Field(min_length=1)


class ApplicabilityDetailPrediction(BaseModel):
    """Validated structured output of the specialized detail prompt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    applicability_statement_confirmed: bool
    applicability_functions: tuple[ApplicabilityFunction, ...] = ()
    evidence: tuple[ApplicabilityDetailEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_prediction(self) -> ApplicabilityDetailPrediction:
        if len(self.applicability_functions) != len(set(self.applicability_functions)):
            raise ValueError("applicability_functions must not contain duplicates")
        evidence_keys = [(item.function, _normalize_text(item.text)) for item in self.evidence]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("applicability detail evidence must not contain duplicates")
        selected = set(self.applicability_functions)
        evidence_functions = {item.function for item in self.evidence}
        if evidence_functions - selected:
            raise ValueError("evidence functions must be included in applicability_functions")
        if selected - evidence_functions:
            raise ValueError("each applicability function requires source evidence")
        if not selected and self.evidence:
            raise ValueError("evidence requires at least one applicability function")
        if not self.applicability_statement_confirmed and (selected or self.evidence):
            raise ValueError(
                "unconfirmed applicability statements require empty detail classifications"
            )
        return self


class ApplicabilityDetailGenerator(BaseModel):
    """Inference provenance for one detail result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    task_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    input_hash: str = Field(min_length=1)
    raw_response_hash: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)
    cached: bool = False
    generated_at: datetime


class ApplicabilityDetailFailure(BaseModel):
    """One isolated detail-enrichment failure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    category: str = Field(min_length=1)
    finish_reason: str | None = None


class ApplicabilityDetailClauseResult(BaseModel):
    """Persisted detail outcome for one Presence-positive clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    example_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reference: str | None = None
    heading: str | None = None
    presence_confidence: float = Field(ge=0.0, le=1.0)
    outcome: ApplicabilityDetailOutcome
    applicability_statement_confirmed: bool | None = None
    applicability_functions: tuple[ApplicabilityFunction, ...] = ()
    evidence: tuple[ApplicabilityDetailEvidence, ...] = ()
    evidence_grounded: bool = False
    generator: ApplicabilityDetailGenerator | None = None
    failure: ApplicabilityDetailFailure | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> ApplicabilityDetailClauseResult:
        if self.outcome is ApplicabilityDetailOutcome.FAILED:
            if self.failure is None:
                raise ValueError("failed detail results require failure information")
            if self.generator is not None:
                raise ValueError("failed detail results must not contain generator information")
            if self.applicability_statement_confirmed is not None:
                raise ValueError("failed detail results have no confirmation decision")
            return self
        if self.failure is not None:
            raise ValueError("non-failed detail results must not contain failure information")
        if self.generator is None:
            raise ValueError("generated detail results require generator information")
        if self.applicability_statement_confirmed is None:
            raise ValueError("generated detail results require a confirmation decision")
        if self.outcome is ApplicabilityDetailOutcome.NOT_CONFIRMED:
            if self.applicability_statement_confirmed:
                raise ValueError("not_confirmed results require an unconfirmed statement")
            if self.applicability_functions or self.evidence:
                raise ValueError("not_confirmed results must not contain detail classifications")
            if not self.evidence_grounded:
                raise ValueError("not_confirmed results carry a grounded empty detail decision")
        elif self.outcome is ApplicabilityDetailOutcome.ENRICHED:
            if not self.applicability_statement_confirmed:
                raise ValueError("enriched detail results require a confirmed statement")
            if not self.applicability_functions or not self.evidence:
                raise ValueError("enriched detail results require functions and evidence")
            if not self.evidence_grounded:
                raise ValueError("enriched detail results require grounded source evidence")
        elif self.outcome is ApplicabilityDetailOutcome.UNRESOLVED:
            if not self.applicability_statement_confirmed:
                raise ValueError("unresolved detail results require a confirmed statement")
            if self.applicability_functions and self.evidence_grounded:
                raise ValueError("resolved grounded classifications use the enriched outcome")
            if not self.applicability_functions and self.evidence:
                raise ValueError("unresolved empty classifications carry empty evidence")
        return self


class ApplicabilityDetailRunStatistics(BaseModel):
    """Execution-specific accounting for one enrichment invocation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attempted_clause_count: int = Field(ge=0)
    reused_clause_count: int = Field(ge=0)
    fresh_prediction_count: int = Field(ge=0)
    cached_prediction_count: int = Field(ge=0)


class ApplicabilityDetailEnrichmentReport(BaseModel):
    """Complete sparse detail-enrichment result for one Presence selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    task: Literal["applicability-detail-enrichment"] = "applicability-detail-enrichment"
    task_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_ref: str = Field(min_length=1)
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime
    selected_clause_count: int = Field(ge=0)
    processed_clause_count: int = Field(ge=0)
    enriched_clause_count: int = Field(ge=0)
    not_confirmed_clause_count: int = Field(ge=0)
    unresolved_clause_count: int = Field(ge=0)
    failed_clause_count: int = Field(ge=0)
    run_statistics: ApplicabilityDetailRunStatistics
    clauses: tuple[ApplicabilityDetailClauseResult, ...]

    @model_validator(mode="after")
    def validate_report(self) -> ApplicabilityDetailEnrichmentReport:
        if self.processed_clause_count != len(self.clauses):
            raise ValueError("processed_clause_count must match clauses")
        if self.processed_clause_count > self.selected_clause_count:
            raise ValueError("processed detail clauses exceed selection")
        counts = {
            ApplicabilityDetailOutcome.ENRICHED: self.enriched_clause_count,
            ApplicabilityDetailOutcome.NOT_CONFIRMED: self.not_confirmed_clause_count,
            ApplicabilityDetailOutcome.UNRESOLVED: self.unresolved_clause_count,
            ApplicabilityDetailOutcome.FAILED: self.failed_clause_count,
        }
        actual = {status: 0 for status in ApplicabilityDetailOutcome}
        for item in self.clauses:
            actual[item.outcome] += 1
        if counts != actual:
            raise ValueError("applicability detail outcome counts do not match clauses")
        coordinates = [(item.document_key, item.clause_id) for item in self.clauses]
        if len(coordinates) != len(set(coordinates)):
            raise ValueError("applicability detail result coordinates must be unique")
        if (
            self.run_statistics.attempted_clause_count + self.run_statistics.reused_clause_count
            != self.processed_clause_count
        ):
            raise ValueError("detail run accounting must match processed clauses")
        generated = (
            self.run_statistics.fresh_prediction_count + self.run_statistics.cached_prediction_count
        )
        if generated > self.run_statistics.attempted_clause_count:
            raise ValueError("generated detail predictions exceed attempted clauses")
        return self


class ApplicabilityDetailFailureReport(BaseModel):
    """Compact retry and review view over failed detail clauses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    task: Literal["applicability-detail-enrichment"] = "applicability-detail-enrichment"
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    failed_clause_count: int = Field(ge=0)
    clauses: tuple[ApplicabilityDetailClauseResult, ...]

    @model_validator(mode="after")
    def validate_failures(self) -> ApplicabilityDetailFailureReport:
        if self.failed_clause_count != len(self.clauses):
            raise ValueError("failed_clause_count must match clauses")
        if any(item.outcome is not ApplicabilityDetailOutcome.FAILED for item in self.clauses):
            raise ValueError("failure report may contain only failed clauses")
        return self


ApplicabilityDetailCheckpoint = Callable[[ApplicabilityDetailEnrichmentReport], None]


def build_applicability_detail_selection(
    *,
    run_selection: QualificationRunSelection,
    examples: tuple[EvaluationExample, ...],
    consensus: ConsensusReport,
    coverage: QualificationCoverage,
    task_version: str,
) -> ApplicabilityDetailSelection:
    """Select exactly the final Presence-positive clauses in persisted run order."""
    if consensus.corpus_id != run_selection.corpus_id:
        raise ValueError(
            "applicability detail consensus corpus differs from persisted run selection"
        )
    if run_selection.selected_clause_count != len(run_selection.clauses):
        raise ValueError("persisted run selection clause count differs from clauses")
    if consensus.clause_count != len(consensus.clauses):
        raise ValueError("final consensus clause count differs from clauses")
    selected_by_coordinate = {
        (item.document_key, item.clause_id): item for item in run_selection.clauses
    }
    if len(selected_by_coordinate) != len(run_selection.clauses):
        raise ValueError("persisted run selection coordinates must be unique")
    examples_by_coordinate = {_example_coordinate(example): example for example in examples}
    if len(examples_by_coordinate) != len(examples):
        raise ValueError("applicability detail example coordinates must be unique")
    if set(examples_by_coordinate) != set(selected_by_coordinate):
        raise ValueError("applicability detail examples differ from persisted run selection")
    consensus_by_coordinate = {
        (item.document_key, item.clause_id): item for item in consensus.clauses
    }
    if len(consensus_by_coordinate) != len(consensus.clauses):
        raise ValueError("applicability detail consensus coordinates must be unique")
    unexpected = set(consensus_by_coordinate) - set(selected_by_coordinate)
    if unexpected:
        raise ValueError("applicability detail consensus contains clauses outside run selection")
    _validate_qualification_coverage(
        run_selection=run_selection,
        coverage=coverage,
        consensus_coordinates=set(consensus_by_coordinate),
    )

    clauses: list[ApplicabilityDetailSelectionClause] = []
    for selection_clause in run_selection.clauses:
        coordinate = (selection_clause.document_key, selection_clause.clause_id)
        consensus_clause = consensus_by_coordinate.get(coordinate)
        if consensus_clause is None or not consensus_clause.applicability_present:
            continue
        example = examples_by_coordinate[coordinate]
        text, content_hash = _example_content(example)
        if not text.strip():
            raise ValueError(
                "applicability detail selection contains empty clause content: "
                f"{selection_clause.document_key}/{selection_clause.clause_id}"
            )
        context = _example_context(example)
        clauses.append(
            ApplicabilityDetailSelectionClause(
                example_id=selection_clause.example_id,
                document_key=selection_clause.document_key,
                clause_id=selection_clause.clause_id,
                content_hash=content_hash,
                reference=consensus_clause.reference or _optional_text(context.get("reference")),
                heading=consensus_clause.heading or _optional_text(context.get("title")),
                presence_confidence=consensus_clause.applicability_presence_confidence,
                presence_category=consensus_clause.applicability_category.value,
                source_requires_review=consensus_clause.requires_review,
                presence_resolution_source=consensus_clause.resolution_sources.get(
                    "applicability", "cumulative-consensus"
                ),
            )
        )
    return ApplicabilityDetailSelection(
        task_version=task_version,
        source_matrix_id=consensus.matrix_id,
        source_corpus_id=consensus.corpus_id,
        source_selection_sha256=_canonical_sha256(run_selection.model_dump(mode="json")),
        source_consensus_sha256=_canonical_sha256(consensus.model_dump(mode="json")),
        source_coverage_sha256=_canonical_sha256(coverage.model_dump(mode="json")),
        source_selected_clause_count=run_selection.selected_clause_count,
        source_qualified_clause_count=coverage.qualified_clause_count,
        source_unqualified_clause_count=coverage.unqualified_clause_count,
        source_consensus_clause_count=len(consensus_by_coordinate),
        selected_clause_count=len(clauses),
        clauses=tuple(clauses),
    )


def _validate_qualification_coverage(
    *,
    run_selection: QualificationRunSelection,
    coverage: QualificationCoverage,
    consensus_coordinates: set[tuple[str, str]],
) -> None:
    """Require final consensus for every clause marked qualified by the run."""
    selected_by_coordinate = {
        (item.document_key, item.clause_id): item.example_id for item in run_selection.clauses
    }
    coverage_by_coordinate = {
        (item.document_key, item.clause_id): item for item in coverage.clauses
    }
    if len(coverage_by_coordinate) != len(coverage.clauses):
        raise ValueError("qualification coverage coordinates must be unique")
    if set(coverage_by_coordinate) != set(selected_by_coordinate):
        raise ValueError("qualification coverage coordinates differ from persisted run selection")
    if any(
        item.example_id != selected_by_coordinate[coordinate]
        for coordinate, item in coverage_by_coordinate.items()
    ):
        raise ValueError("qualification coverage example ids differ from run selection")

    qualified_coordinates = {
        coordinate
        for coordinate, item in coverage_by_coordinate.items()
        if item.status == "qualified"
    }
    qualified_count = len(qualified_coordinates)
    unqualified_count = len(coverage_by_coordinate) - qualified_count
    if (
        coverage.selected_clause_count != run_selection.selected_clause_count
        or coverage.accounted_clause_count != run_selection.selected_clause_count
        or coverage.qualified_clause_count != qualified_count
        or coverage.unqualified_clause_count != unqualified_count
    ):
        raise ValueError("qualification coverage accounting differs from persisted run selection")
    if consensus_coordinates != qualified_coordinates:
        missing = qualified_coordinates - consensus_coordinates
        unexpected = consensus_coordinates - qualified_coordinates
        details: list[str] = []
        if missing:
            details.append(f"missing={len(missing)}")
        if unexpected:
            details.append(f"unexpected={len(unexpected)}")
        raise ValueError(
            "final consensus coordinates differ from qualified coverage: " + ", ".join(details)
        )


class ApplicabilityDetailEnrichmentService:
    """Run one specialized prompt only for final Presence-positive clauses."""

    def __init__(
        self,
        gateway: LlmGateway,
        *,
        config: ApplicabilityDetailEnrichmentConfig,
        prompt: PromptDefinition,
        canonical_schema: Mapping[str, Any],
        model_id: str,
        model_ref: str,
        artifact_root: Path | None = None,
    ) -> None:
        if prompt.task != config.task:
            raise ValueError(
                f"applicability detail prompt task mismatch: {prompt.task} != {config.task}"
            )
        if prompt.version != config.prompt_version:
            raise ValueError(
                "applicability detail prompt version differs from manifest configuration"
            )
        if dict(prompt.output_schema) != dict(canonical_schema):
            raise ValueError("applicability detail prompt schema differs from task schema")
        self._gateway = gateway
        self._config = config
        self._prompt = prompt
        self._schema = dict(canonical_schema)
        self._model_id = model_id
        self._model_ref = model_ref
        self._artifact_root = artifact_root

    def pending_clause_count(
        self,
        *,
        selection: ApplicabilityDetailSelection,
        existing: ApplicabilityDetailEnrichmentReport | None = None,
        fresh: bool = False,
    ) -> int:
        """Count clauses that require provider inference for this invocation."""
        config_sha256 = _canonical_sha256(self._config.model_dump(mode="json"))
        self._validate_existing_report(
            selection=selection,
            existing=existing,
            fresh=fresh,
            config_sha256=config_sha256,
        )
        existing_by_coordinate = {
            (item.document_key, item.clause_id): item
            for item in (existing.clauses if existing is not None else ())
        }
        return sum(
            not _detail_result_is_reusable(
                existing_by_coordinate.get((selected.document_key, selected.clause_id)),
                selected=selected,
                fresh=fresh,
            )
            for selected in selection.clauses
        )

    def enrich(
        self,
        *,
        selection: ApplicabilityDetailSelection,
        examples: tuple[EvaluationExample, ...],
        existing: ApplicabilityDetailEnrichmentReport | None = None,
        fresh: bool = False,
        checkpoint: ApplicabilityDetailCheckpoint | None = None,
    ) -> ApplicabilityDetailEnrichmentReport:
        """Enrich selected clauses, reusing completed results and retrying failures."""
        config_sha256 = _canonical_sha256(self._config.model_dump(mode="json"))
        self._validate_existing_report(
            selection=selection,
            existing=existing,
            fresh=fresh,
            config_sha256=config_sha256,
        )

        examples_by_coordinate = {_example_coordinate(item): item for item in examples}
        selection_coordinates = {(item.document_key, item.clause_id) for item in selection.clauses}
        if not selection_coordinates.issubset(examples_by_coordinate):
            raise ValueError("applicability detail selection is missing source examples")

        existing_by_coordinate = {
            (item.document_key, item.clause_id): item
            for item in (existing.clauses if existing is not None else ())
        }
        results: list[ApplicabilityDetailClauseResult] = []
        attempted = 0
        reused = 0
        fresh_predictions = 0
        cached_predictions = 0
        for selected in selection.clauses:
            coordinate = (selected.document_key, selected.clause_id)
            previous = existing_by_coordinate.get(coordinate)
            if _detail_result_is_reusable(
                previous,
                selected=selected,
                fresh=fresh,
            ):
                results.append(previous)
                reused += 1
            else:
                attempted += 1
                result, generated_fresh, generated_cached = self._enrich_clause(
                    selected, examples_by_coordinate[coordinate]
                )
                results.append(result)
                fresh_predictions += generated_fresh
                cached_predictions += generated_cached
            report = _build_report(
                selection=selection,
                config=self._config,
                model_id=self._model_id,
                model_ref=self._model_ref,
                config_sha256=config_sha256,
                results=tuple(results),
                attempted=attempted,
                reused=reused,
                fresh_predictions=fresh_predictions,
                cached_predictions=cached_predictions,
            )
            if checkpoint is not None:
                checkpoint(report)
        return _build_report(
            selection=selection,
            config=self._config,
            model_id=self._model_id,
            model_ref=self._model_ref,
            config_sha256=config_sha256,
            results=tuple(results),
            attempted=attempted,
            reused=reused,
            fresh_predictions=fresh_predictions,
            cached_predictions=cached_predictions,
        )

    def _validate_existing_report(
        self,
        *,
        selection: ApplicabilityDetailSelection,
        existing: ApplicabilityDetailEnrichmentReport | None,
        fresh: bool,
        config_sha256: str,
    ) -> None:
        if existing is None or fresh:
            return
        if existing.selection_sha256 != selection.fingerprint:
            raise ValueError(
                "existing applicability detail report belongs to a different selection; "
                "use --fresh to replace it"
            )
        if existing.config_sha256 != config_sha256:
            raise ValueError(
                "existing applicability detail report belongs to a different configuration; "
                "use --fresh to replace it"
            )
        if existing.model_id != self._model_id or existing.model_ref != self._model_ref:
            raise ValueError(
                "existing applicability detail report belongs to a different model; "
                "use --fresh to replace it"
            )

    def _enrich_clause(
        self,
        selected: ApplicabilityDetailSelectionClause,
        example: EvaluationExample,
    ) -> tuple[ApplicabilityDetailClauseResult, int, int]:
        text, content_hash = _example_content(example)
        if content_hash != selected.content_hash:
            raise ValueError(
                "applicability detail source content changed for "
                f"{selected.document_key}/{selected.clause_id}"
            )
        values = {
            "content": text,
            "content_hash": content_hash,
            "document_key": selected.document_key,
            "clause_id": selected.clause_id,
            "reference": selected.reference or "",
            "heading": selected.heading or "",
        }
        try:
            user_prompt = self._prompt.user_template.format(**values)
        except KeyError as exc:
            raise ValueError(
                f"applicability detail prompt references unavailable field: {exc.args[0]}"
            ) from exc
        request = StructuredGenerationRequest(
            task=self._config.task,
            system_prompt=self._prompt.system_prompt,
            user_prompt=user_prompt,
            output_schema=self._schema,
            prompt_version=self._config.prompt_version,
            model=self._model_ref,
            temperature=0.0,
            seed=0,
            max_tokens=self._config.max_output_tokens,
            reasoning_enabled=False,
            metadata={
                "task_version": self._config.task_version,
                "selection_clause": selected.model_dump(mode="json"),
            },
        )
        case_root = self._case_artifact_root(selected)
        if case_root is not None:
            case_root.mkdir(parents=True, exist_ok=True)
            (case_root / "response.json").unlink(missing_ok=True)
            (case_root / "failure.json").unlink(missing_ok=True)
            _write_json(case_root / "request.json", _serialize_request(request))
        try:
            generated = generate_with_retry(
                self._gateway,
                request,
                attempts=self._config.retry_attempts,
                backoff_seconds=self._config.retry_backoff_seconds,
                retry_timeouts=self._config.retry_timeouts,
                truncation_retry_max_tokens=self._config.truncation_retry_max_tokens,
                retry_on_truncation=True,
            )
            if case_root is not None:
                _write_json(case_root / "response.json", _serialize_response(generated))
                (case_root / "failure.json").unlink(missing_ok=True)
            valid, error = validate_schema(generated.value, self._schema)
            if not valid:
                raise ValueError(f"provider response violates task schema: {error}")
            prediction = _canonicalize_prediction(
                ApplicabilityDetailPrediction.model_validate(generated.value)
            )
            grounded = all(_evidence_is_grounded(item.text, text) for item in prediction.evidence)
            if not prediction.applicability_statement_confirmed:
                outcome = ApplicabilityDetailOutcome.NOT_CONFIRMED
                grounded = True
            elif not prediction.applicability_functions:
                outcome = ApplicabilityDetailOutcome.UNRESOLVED
                grounded = True
            elif grounded:
                outcome = ApplicabilityDetailOutcome.ENRICHED
            else:
                outcome = ApplicabilityDetailOutcome.UNRESOLVED
            result = ApplicabilityDetailClauseResult(
                example_id=selected.example_id,
                document_key=selected.document_key,
                clause_id=selected.clause_id,
                content_hash=selected.content_hash,
                reference=selected.reference,
                heading=selected.heading,
                presence_confidence=selected.presence_confidence,
                outcome=outcome,
                applicability_statement_confirmed=(prediction.applicability_statement_confirmed),
                applicability_functions=prediction.applicability_functions,
                evidence=prediction.evidence,
                evidence_grounded=grounded,
                generator=_generator(
                    generated,
                    model_id=self._model_id,
                    task_version=self._config.task_version,
                ),
            )
            return result, int(not generated.cached), int(generated.cached)
        except Exception as exc:  # isolate sparse enrichment failures per clause
            failure = ApplicabilityDetailFailure(
                error_type=type(exc).__name__,
                message=str(exc) or type(exc).__name__,
                category=_failure_category(exc),
                finish_reason=getattr(exc, "finish_reason", None),
            )
            if case_root is not None:
                _write_json(
                    case_root / "failure.json",
                    {
                        "clause": selected.model_dump(mode="json"),
                        "error": failure.model_dump(mode="json"),
                        "raw_content": getattr(exc, "raw_content", None),
                        "raw_response": getattr(exc, "raw_response", None),
                    },
                )
            return (
                ApplicabilityDetailClauseResult(
                    example_id=selected.example_id,
                    document_key=selected.document_key,
                    clause_id=selected.clause_id,
                    content_hash=selected.content_hash,
                    reference=selected.reference,
                    heading=selected.heading,
                    presence_confidence=selected.presence_confidence,
                    outcome=ApplicabilityDetailOutcome.FAILED,
                    failure=failure,
                ),
                0,
                0,
            )

    def _case_artifact_root(self, selected: ApplicabilityDetailSelectionClause) -> Path | None:
        if self._artifact_root is None:
            return None
        return self._artifact_root / "clauses" / _safe(selected.example_id)


def persist_applicability_detail_selection(
    selection: ApplicabilityDetailSelection, path: Path
) -> Path:
    """Persist the deterministic positive Selection."""
    _write_json(path, selection.model_dump(mode="json"))
    return path


def load_applicability_detail_selection(path: Path) -> ApplicabilityDetailSelection:
    return ApplicabilityDetailSelection.model_validate_json(path.read_text(encoding="utf-8"))


def persist_applicability_detail_report(
    report: ApplicabilityDetailEnrichmentReport,
    report_path: Path,
    failure_path: Path,
) -> tuple[Path, Path]:
    """Persist full results and a compact failure-only projection."""
    _write_json(report_path, report.model_dump(mode="json"))
    failures = tuple(
        item for item in report.clauses if item.outcome is ApplicabilityDetailOutcome.FAILED
    )
    failure_report = ApplicabilityDetailFailureReport(
        selection_sha256=report.selection_sha256,
        failed_clause_count=len(failures),
        clauses=failures,
    )
    _write_json(failure_path, failure_report.model_dump(mode="json"))
    return report_path, failure_path


def load_applicability_detail_report(path: Path) -> ApplicabilityDetailEnrichmentReport:
    return ApplicabilityDetailEnrichmentReport.model_validate_json(path.read_text(encoding="utf-8"))


def _detail_result_is_reusable(
    previous: ApplicabilityDetailClauseResult | None,
    *,
    selected: ApplicabilityDetailSelectionClause,
    fresh: bool,
) -> bool:
    return bool(
        not fresh
        and previous is not None
        and previous.outcome is not ApplicabilityDetailOutcome.FAILED
        and previous.content_hash == selected.content_hash
    )


def _build_report(
    *,
    selection: ApplicabilityDetailSelection,
    config: ApplicabilityDetailEnrichmentConfig,
    model_id: str,
    model_ref: str,
    config_sha256: str,
    results: tuple[ApplicabilityDetailClauseResult, ...],
    attempted: int,
    reused: int,
    fresh_predictions: int,
    cached_predictions: int,
) -> ApplicabilityDetailEnrichmentReport:
    counts = {status: 0 for status in ApplicabilityDetailOutcome}
    for result in results:
        counts[result.outcome] += 1
    return ApplicabilityDetailEnrichmentReport(
        task_version=config.task_version,
        prompt_version=config.prompt_version,
        model_id=model_id,
        model_ref=model_ref,
        selection_sha256=selection.fingerprint,
        config_sha256=config_sha256,
        generated_at=datetime.now(UTC),
        selected_clause_count=selection.selected_clause_count,
        processed_clause_count=len(results),
        enriched_clause_count=counts[ApplicabilityDetailOutcome.ENRICHED],
        not_confirmed_clause_count=counts[ApplicabilityDetailOutcome.NOT_CONFIRMED],
        unresolved_clause_count=counts[ApplicabilityDetailOutcome.UNRESOLVED],
        failed_clause_count=counts[ApplicabilityDetailOutcome.FAILED],
        run_statistics=ApplicabilityDetailRunStatistics(
            attempted_clause_count=attempted,
            reused_clause_count=reused,
            fresh_prediction_count=fresh_predictions,
            cached_prediction_count=cached_predictions,
        ),
        clauses=results,
    )


def _canonicalize_prediction(
    prediction: ApplicabilityDetailPrediction,
) -> ApplicabilityDetailPrediction:
    order = {value: index for index, value in enumerate(ApplicabilityFunction)}
    return prediction.model_copy(
        update={
            "applicability_functions": tuple(
                sorted(prediction.applicability_functions, key=order.__getitem__)
            ),
            "evidence": tuple(
                sorted(
                    prediction.evidence,
                    key=lambda item: (order[item.function], _normalize_text(item.text)),
                )
            ),
        }
    )


def _generator(
    result: StructuredGenerationResult,
    *,
    model_id: str,
    task_version: str,
) -> ApplicabilityDetailGenerator:
    return ApplicabilityDetailGenerator(
        model_id=model_id,
        model=result.model,
        provider=result.provider,
        task_version=task_version,
        prompt_version=result.prompt_version,
        input_hash=result.input_hash,
        raw_response_hash=result.raw_response_hash,
        duration_ms=result.duration_ms,
        cached=result.cached,
        generated_at=datetime.now(UTC),
    )


def _example_coordinate(example: EvaluationExample) -> tuple[str, str]:
    context = _example_context(example)
    document_key = context.get("document_key")
    clause_id = context.get("clause_id")
    if not isinstance(document_key, str) or not document_key:
        raise ValueError(f"evaluation example {example.id!r} has no document_key")
    if not isinstance(clause_id, str) or not clause_id:
        raise ValueError(f"evaluation example {example.id!r} has no clause_id")
    return document_key, clause_id


def _example_context(example: EvaluationExample) -> dict[str, Any]:
    raw = example.input.get("context")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _example_content(example: EvaluationExample) -> tuple[str, str]:
    raw = example.input.get("content", "")
    if isinstance(raw, Mapping):
        text = str(raw.get("text") or "")
        supplied_hash = raw.get("hash")
    else:
        text = str(raw or "")
        supplied_hash = None
    calculated = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    if isinstance(supplied_hash, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", supplied_hash):
        if supplied_hash != calculated:
            raise ValueError("evaluation example content hash differs from normalized content")
        return text, supplied_hash
    return text, calculated


def _evidence_is_grounded(evidence: str, content: str) -> bool:
    needle = _collapse_whitespace(evidence)
    return bool(needle) and needle in _collapse_whitespace(content)


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_text(value: str) -> str:
    return _collapse_whitespace(value).casefold()


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _failure_category(exc: Exception) -> str:
    name = type(exc).__name__
    if name == "LlmTimeoutError":
        return "timeout"
    if name == "LlmUnavailableError":
        return "unavailable"
    if name == "LlmResponseError":
        return "invalid_response"
    if isinstance(exc, ValueError):
        return "validation"
    return "unexpected"


def _serialize_request(request: StructuredGenerationRequest) -> dict[str, Any]:
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


def _serialize_response(result: StructuredGenerationResult) -> dict[str, Any]:
    return {
        "value": dict(result.value),
        "model": result.model,
        "provider": result.provider,
        "prompt_version": result.prompt_version,
        "input_hash": result.input_hash,
        "raw_response_hash": result.raw_response_hash,
        "duration_ms": result.duration_ms,
        "cached": result.cached,
        "usage": vars(result.usage) if result.usage is not None else None,
        "raw_response": result.raw_response,
    }


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "clause"
