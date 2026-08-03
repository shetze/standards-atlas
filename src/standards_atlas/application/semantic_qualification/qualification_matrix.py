"""Model and prompt qualification matrices for semantic annotation runs."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, pstdev

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.qualification import (
    AnnotationQualificationReport,
)

_PROMPT_VERSION_ALIASES = {
    "content-only": "content-only-v1",
    "structure-aware": "structure-aware-v1",
    "reference-aware": "evidence-first-v1",
    "bounded-reasoning": "bounded-reasoning-v1",
    "deliberative": "bounded-reasoning-v1",
}


class PromptCandidate(BaseModel):
    """One versioned prompt variant in the qualification shortlist."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    description: str = ""
    definition: Path | None = None
    prompt_version: str | None = None
    max_output_tokens: int = Field(default=512, gt=0)
    adaptive_interview: bool = False


def resolve_prompt_version(
    prompt: PromptCandidate,
    *,
    resources: Path,
    task: str = "statement-function-classification",
) -> str:
    """Resolve a matrix prompt id to an installed prompt resource version."""
    candidates = [prompt.prompt_version, _PROMPT_VERSION_ALIASES.get(prompt.id), prompt.id]
    checked: list[str] = []
    for candidate in candidates:
        if not candidate or candidate in checked:
            continue
        checked.append(candidate)
        definition = resources / "prompts" / task / candidate / "prompt.json"
        if definition.is_file():
            return candidate
    available_root = resources / "prompts" / task
    available = (
        sorted(path.name for path in available_root.iterdir() if path.is_dir())
        if available_root.is_dir()
        else []
    )
    raise ValueError(
        f"prompt {prompt.id!r} cannot be resolved; checked {checked}; "
        f"available versions: {available}"
    )


class ModelCandidate(BaseModel):
    """One model/provider combination and its declared resource profile."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model_ref: str | None = None
    quantization: str | None = None
    description: str = ""
    accelerator: str | None = None
    parameters_billion: float | None = Field(default=None, gt=0.0)
    declared_memory_gb: float | None = Field(default=None, gt=0.0)
    repetitions: int | None = Field(default=None, ge=0)


class ReasoningMode(BaseModel):
    """Optional reasoning configuration evaluated as a third matrix dimension."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    enabled: bool = False
    optional: bool = False
    description: str = ""


class MatrixObservation(BaseModel):
    """One repeated model/prompt run and its 5.4.5 qualification report."""

    model_config = ConfigDict(frozen=True)

    prompt_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    reasoning_mode_id: str = "disabled"
    repetition: int = Field(ge=1)
    qualification_report: Path
    run_directory: Path | None = None
    mean_duration_seconds: float | None = Field(default=None, ge=0.0)
    peak_memory_gb: float | None = Field(default=None, ge=0.0)


class RegressionThresholds(BaseModel):
    """Project-owned acceptance thresholds for qualification candidates."""

    model_config = ConfigDict(frozen=True)

    min_gold_f1: float = Field(default=0.0, ge=0.0, le=1.0)
    min_gold_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    max_gold_f1_stddev: float = Field(default=1.0, ge=0.0, le=1.0)
    min_prediction_success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    min_json_validity_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    max_truncation_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    max_mean_duration_seconds: float | None = Field(default=None, gt=0.0)
    max_peak_memory_gb: float | None = Field(default=None, gt=0.0)
    baseline_prompt_id: str | None = None
    baseline_model_id: str | None = None
    baseline_reasoning_mode_id: str = "disabled"
    max_gold_f1_drop: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_complete_baseline(self) -> RegressionThresholds:
        if bool(self.baseline_prompt_id) != bool(self.baseline_model_id):
            raise ValueError("baseline_prompt_id and baseline_model_id must be set together")
        return self


class ReviewImportConfig(BaseModel):
    """Existing HITL review imported before matrix execution."""

    model_config = ConfigDict(frozen=True)

    run_directory: Path
    review_directory: Path
    local_corpus_root: Path = Path("local/evaluation/corpora")
    overwrite: bool = False
    required: bool = True


class ConsensusConfig(BaseModel):
    """Cross-model consensus settings for a new Golden Corpus proposal."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    prompt_id: str = "content-only"
    reasoning_mode_id: str = "disabled"
    min_models: int = Field(default=3, ge=2)
    strong_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    majority_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    label_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    output_directory: Path = Path("local/evaluation/consensus")


class QualificationMatrixManifest(BaseModel):
    """Versioned contract for Slice 5.4.6 qualification."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    matrix_id: str = Field(min_length=1)
    corpus_id: str = Field(min_length=1)
    task_version: str = Field(default="1.0.0", min_length=1)
    dataset_version: str = Field(default="1.0.0", min_length=1)
    repetitions: int = Field(default=3, ge=1)
    prompts: tuple[PromptCandidate, ...]
    models: tuple[ModelCandidate, ...] = Field(min_length=1)
    reasoning_modes: tuple[ReasoningMode, ...] = (ReasoningMode(id="disabled"),)
    observations: tuple[MatrixObservation, ...] = ()
    review_imports: tuple[ReviewImportConfig, ...] = ()
    consensus: ConsensusConfig = ConsensusConfig()
    thresholds: RegressionThresholds = RegressionThresholds()

    def repetitions_for(self, model: ModelCandidate) -> int:
        """Return the model-specific repetition count or the global default."""
        return model.repetitions if model.repetitions is not None else self.repetitions

    @model_validator(mode="after")
    def validate_matrix(self) -> QualificationMatrixManifest:
        if len(self.prompts) != 4:
            raise ValueError("qualification matrix must declare exactly four prompt variants")
        prompt_ids = [item.id for item in self.prompts]
        model_ids = [item.id for item in self.models]
        reasoning_mode_ids = [item.id for item in self.reasoning_modes]
        if len(set(prompt_ids)) != len(prompt_ids):
            raise ValueError("prompt candidate ids must be unique")
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("model candidate ids must be unique")
        if not reasoning_mode_ids:
            raise ValueError("at least one reasoning mode must be declared")
        if len(set(reasoning_mode_ids)) != len(reasoning_mode_ids):
            raise ValueError("reasoning mode ids must be unique")
        model_repetitions = {item.id: self.repetitions_for(item) for item in self.models}
        seen: set[tuple[str, str, str, int]] = set()
        for item in self.observations:
            if item.prompt_id not in prompt_ids:
                raise ValueError(f"unknown prompt_id in observation: {item.prompt_id}")
            if item.model_id not in model_ids:
                raise ValueError(f"unknown model_id in observation: {item.model_id}")
            if item.reasoning_mode_id not in reasoning_mode_ids:
                raise ValueError(
                    f"unknown reasoning_mode_id in observation: {item.reasoning_mode_id}"
                )
            expected_repetitions = model_repetitions[item.model_id]
            if expected_repetitions == 0:
                raise ValueError(
                    f"observation repetition {item.repetition} exceeds "
                    f"configured repetitions 0 for {item.model_id}"
                )
            key = (
                item.prompt_id,
                item.model_id,
                item.reasoning_mode_id,
                item.repetition,
            )
            if key in seen:
                raise ValueError(f"duplicate matrix observation: {key}")
            seen.add(key)
        return self

    @classmethod
    def load(cls, path: Path) -> QualificationMatrixManifest:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        manifest = cls.model_validate(payload)
        base = path.parent
        observations = tuple(
            item.model_copy(
                update={
                    "qualification_report": (
                        item.qualification_report
                        if item.qualification_report.is_absolute()
                        else base / item.qualification_report
                    ),
                    "run_directory": (
                        None
                        if item.run_directory is None
                        else item.run_directory
                        if item.run_directory.is_absolute()
                        else base / item.run_directory
                    ),
                }
            )
            for item in manifest.observations
        )
        review_imports = tuple(
            item.model_copy(
                update={
                    "run_directory": (
                        item.run_directory
                        if item.run_directory.is_absolute()
                        else base / item.run_directory
                    ),
                    "review_directory": (
                        item.review_directory
                        if item.review_directory.is_absolute()
                        else base / item.review_directory
                    ),
                    "local_corpus_root": (
                        item.local_corpus_root
                        if item.local_corpus_root.is_absolute()
                        else base / item.local_corpus_root
                    ),
                }
            )
            for item in manifest.review_imports
        )
        consensus = manifest.consensus.model_copy(
            update={
                "output_directory": (
                    manifest.consensus.output_directory
                    if manifest.consensus.output_directory.is_absolute()
                    else base / manifest.consensus.output_directory
                )
            }
        )
        return manifest.model_copy(
            update={
                "observations": observations,
                "review_imports": review_imports,
                "consensus": consensus,
            }
        )


class CandidateQualification(BaseModel):
    """Aggregated result for one model/prompt candidate."""

    model_config = ConfigDict(frozen=True)

    prompt_id: str
    model_id: str
    provider: str
    reasoning_mode_id: str
    reasoning_optional: bool
    expected_repetitions: int
    completed_repetitions: int
    mean_gold_f1: float
    min_gold_f1: float
    gold_f1_stddev: float
    mean_gold_coverage: float
    mean_silver_f1: float
    mean_structure_f1: float
    mean_prediction_success_rate: float
    mean_json_validity_rate: float
    mean_truncation_rate: float
    mean_duration_seconds: float | None = None
    peak_memory_gb: float | None = None
    pareto_optimal: bool = False
    passed: bool
    regressions: tuple[str, ...] = ()


class QualificationMatrixReport(BaseModel):
    """Machine-readable comparison and acceptance result."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    matrix_id: str
    corpus_id: str
    generated_at: datetime
    passed: bool
    ranking: tuple[str, ...]
    pareto_front: tuple[str, ...]
    candidates: tuple[CandidateQualification, ...]
    diagnostics: tuple[str, ...] = ()


class ModelPromptQualificationService:
    """Aggregate repeated qualification reports and enforce regression gates."""

    def evaluate(
        self,
        manifest: QualificationMatrixManifest,
        output_directory: Path,
    ) -> tuple[QualificationMatrixReport, Path, Path]:
        grouped: dict[
            tuple[str, str, str],
            list[tuple[MatrixObservation, AnnotationQualificationReport]],
        ] = {}
        diagnostics: list[str] = []
        for observation in manifest.observations:
            report = AnnotationQualificationReport.model_validate_json(
                observation.qualification_report.read_text(encoding="utf-8")
            )
            if report.corpus_id != manifest.corpus_id:
                raise ValueError(
                    f"corpus mismatch in {observation.qualification_report}: "
                    f"{report.corpus_id} != {manifest.corpus_id}"
                )
            grouped.setdefault(
                (
                    observation.prompt_id,
                    observation.model_id,
                    observation.reasoning_mode_id,
                ),
                [],
            ).append((observation, report))

        model_map = {item.id: item for item in manifest.models}
        raw_candidates: list[CandidateQualification] = []
        for prompt in manifest.prompts:
            for model in manifest.models:
                if manifest.repetitions_for(model) == 0:
                    continue
                for reasoning_mode in manifest.reasoning_modes:
                    entries = sorted(
                        grouped.get((prompt.id, model.id, reasoning_mode.id), []),
                        key=lambda item: item[0].repetition,
                    )
                    candidate = _aggregate_candidate(
                        prompt.id,
                        model,
                        reasoning_mode,
                        entries,
                        manifest.repetitions_for(model),
                        manifest.thresholds,
                    )
                    raw_candidates.append(candidate)
                    if not entries and not reasoning_mode.optional:
                        diagnostics.append(
                            f"missing all runs for {prompt.id} / {model.id} / {reasoning_mode.id}"
                        )

        baseline = _baseline(raw_candidates, manifest.thresholds)
        candidates = tuple(
            _apply_baseline_threshold(item, baseline, manifest.thresholds)
            for item in raw_candidates
        )
        pareto_keys = _pareto_front(candidates)
        candidates = tuple(
            item.model_copy(update={"pareto_optimal": _candidate_key(item) in pareto_keys})
            for item in candidates
        )
        ranking = tuple(
            _candidate_key(item)
            for item in sorted(
                candidates,
                key=lambda item: (
                    item.passed,
                    item.mean_gold_f1,
                    -item.gold_f1_stddev,
                    item.mean_gold_coverage,
                    -(item.mean_duration_seconds or math.inf),
                ),
                reverse=True,
            )
        )
        report = QualificationMatrixReport(
            matrix_id=manifest.matrix_id,
            corpus_id=manifest.corpus_id,
            generated_at=datetime.now(UTC),
            passed=all(item.passed for item in candidates if not item.reasoning_optional),
            ranking=ranking,
            pareto_front=tuple(key for key in ranking if key in pareto_keys),
            candidates=candidates,
            diagnostics=tuple(diagnostics),
        )
        output_directory.mkdir(parents=True, exist_ok=True)
        json_path = output_directory / "qualification-matrix.json"
        markdown_path = output_directory / "qualification-matrix.md"
        json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        markdown_path.write_text(_markdown(report, model_map), encoding="utf-8")
        return report, json_path, markdown_path


def _aggregate_candidate(
    prompt_id: str,
    model: ModelCandidate,
    reasoning_mode: ReasoningMode,
    entries: list[tuple[MatrixObservation, AnnotationQualificationReport]],
    expected_repetitions: int,
    thresholds: RegressionThresholds,
) -> CandidateQualification:
    f1_values = [item.gold_agreement.micro_f1 for _, item in entries]
    coverage_values = [item.gold_agreement.coverage for _, item in entries]
    silver_values = [item.silver_agreement.micro_f1 for _, item in entries]
    structure_values = [item.structure_agreement.micro_f1 for _, item in entries]
    success_values = [item.reliability.prediction_success_rate for _, item in entries]
    json_values = [item.reliability.json_validity_rate for _, item in entries]
    truncation_values = [item.reliability.truncation_rate for _, item in entries]
    durations = [item.mean_duration_seconds for item, _ in entries if item.mean_duration_seconds]
    memory = [item.peak_memory_gb for item, _ in entries if item.peak_memory_gb is not None]
    regressions: list[str] = []
    if not entries and reasoning_mode.optional:
        return CandidateQualification(
            prompt_id=prompt_id,
            model_id=model.id,
            provider=model.provider,
            reasoning_mode_id=reasoning_mode.id,
            reasoning_optional=True,
            expected_repetitions=expected_repetitions,
            completed_repetitions=0,
            mean_gold_f1=0.0,
            min_gold_f1=0.0,
            gold_f1_stddev=0.0,
            mean_gold_coverage=0.0,
            mean_silver_f1=0.0,
            mean_structure_f1=0.0,
            mean_prediction_success_rate=0.0,
            mean_json_validity_rate=0.0,
            mean_truncation_rate=0.0,
            peak_memory_gb=model.declared_memory_gb,
            passed=True,
        )
    if len(entries) != expected_repetitions and not reasoning_mode.optional:
        regressions.append(
            f"completed repetitions {len(entries)} != expected {expected_repetitions}"
        )
    mean_f1 = fmean(f1_values) if f1_values else 0.0
    minimum_f1 = min(f1_values) if f1_values else 0.0
    stddev = pstdev(f1_values) if len(f1_values) > 1 else 0.0
    mean_coverage = fmean(coverage_values) if coverage_values else 0.0
    mean_duration = fmean(durations) if durations else None
    peak_memory = max(memory) if memory else model.declared_memory_gb
    if mean_f1 < thresholds.min_gold_f1:
        regressions.append(f"mean Gold F1 {mean_f1:.4f} < {thresholds.min_gold_f1:.4f}")
    if mean_coverage < thresholds.min_gold_coverage:
        regressions.append(
            f"mean Gold coverage {mean_coverage:.4f} < {thresholds.min_gold_coverage:.4f}"
        )
    mean_success = fmean(success_values) if success_values else 0.0
    mean_json = fmean(json_values) if json_values else 0.0
    mean_truncation = fmean(truncation_values) if truncation_values else 0.0
    if mean_success < thresholds.min_prediction_success_rate:
        regressions.append(
            f"prediction success rate {mean_success:.4f} < "
            f"{thresholds.min_prediction_success_rate:.4f}"
        )
    if mean_json < thresholds.min_json_validity_rate:
        regressions.append(
            f"JSON validity rate {mean_json:.4f} < {thresholds.min_json_validity_rate:.4f}"
        )
    if mean_truncation > thresholds.max_truncation_rate:
        regressions.append(
            f"truncation rate {mean_truncation:.4f} > {thresholds.max_truncation_rate:.4f}"
        )
    if stddev > thresholds.max_gold_f1_stddev:
        regressions.append(f"Gold F1 stddev {stddev:.4f} > {thresholds.max_gold_f1_stddev:.4f}")
    if (
        thresholds.max_mean_duration_seconds is not None
        and mean_duration is not None
        and mean_duration > thresholds.max_mean_duration_seconds
    ):
        regressions.append(
            f"mean duration {mean_duration:.3f}s > {thresholds.max_mean_duration_seconds:.3f}s"
        )
    if (
        thresholds.max_peak_memory_gb is not None
        and peak_memory is not None
        and peak_memory > thresholds.max_peak_memory_gb
    ):
        regressions.append(
            f"peak memory {peak_memory:.3f}GB > {thresholds.max_peak_memory_gb:.3f}GB"
        )
    return CandidateQualification(
        prompt_id=prompt_id,
        model_id=model.id,
        provider=model.provider,
        reasoning_mode_id=reasoning_mode.id,
        reasoning_optional=reasoning_mode.optional,
        expected_repetitions=expected_repetitions,
        completed_repetitions=len(entries),
        mean_gold_f1=mean_f1,
        min_gold_f1=minimum_f1,
        gold_f1_stddev=stddev,
        mean_gold_coverage=mean_coverage,
        mean_silver_f1=fmean(silver_values) if silver_values else 0.0,
        mean_structure_f1=fmean(structure_values) if structure_values else 0.0,
        mean_prediction_success_rate=mean_success,
        mean_json_validity_rate=mean_json,
        mean_truncation_rate=mean_truncation,
        mean_duration_seconds=mean_duration,
        peak_memory_gb=peak_memory,
        passed=not regressions,
        regressions=tuple(regressions),
    )


def _baseline(
    candidates: list[CandidateQualification], thresholds: RegressionThresholds
) -> CandidateQualification | None:
    if thresholds.baseline_prompt_id is None or thresholds.baseline_model_id is None:
        return None
    return next(
        (
            item
            for item in candidates
            if item.prompt_id == thresholds.baseline_prompt_id
            and item.model_id == thresholds.baseline_model_id
            and item.reasoning_mode_id == thresholds.baseline_reasoning_mode_id
        ),
        None,
    )


def _apply_baseline_threshold(
    candidate: CandidateQualification,
    baseline: CandidateQualification | None,
    thresholds: RegressionThresholds,
) -> CandidateQualification:
    if baseline is None:
        return candidate
    minimum = baseline.mean_gold_f1 - thresholds.max_gold_f1_drop
    if candidate.mean_gold_f1 >= minimum:
        return candidate
    regressions = candidate.regressions + (
        f"mean Gold F1 {candidate.mean_gold_f1:.4f} < baseline allowance {minimum:.4f}",
    )
    return candidate.model_copy(update={"passed": False, "regressions": regressions})


def _candidate_key(candidate: CandidateQualification) -> str:
    return f"{candidate.prompt_id} / {candidate.model_id} / {candidate.reasoning_mode_id}"


def _pareto_front(candidates: tuple[CandidateQualification, ...]) -> set[str]:
    complete = [item for item in candidates if item.completed_repetitions > 0]
    front: set[str] = set()
    for candidate in complete:
        dominated = any(
            other is not candidate and _dominates(other, candidate) for other in complete
        )
        if not dominated:
            front.add(_candidate_key(candidate))
    return front


def _dominates(left: CandidateQualification, right: CandidateQualification) -> bool:
    left_duration = (
        left.mean_duration_seconds if left.mean_duration_seconds is not None else math.inf
    )
    right_duration = (
        right.mean_duration_seconds if right.mean_duration_seconds is not None else math.inf
    )
    left_memory = left.peak_memory_gb if left.peak_memory_gb is not None else math.inf
    right_memory = right.peak_memory_gb if right.peak_memory_gb is not None else math.inf
    no_worse = (
        left.mean_gold_f1 >= right.mean_gold_f1
        and left.gold_f1_stddev <= right.gold_f1_stddev
        and left_duration <= right_duration
        and left_memory <= right_memory
    )
    strictly_better = (
        left.mean_gold_f1 > right.mean_gold_f1
        or left.gold_f1_stddev < right.gold_f1_stddev
        or left_duration < right_duration
        or left_memory < right_memory
    )
    return no_worse and strictly_better


def _markdown(report: QualificationMatrixReport, models: dict[str, ModelCandidate]) -> str:
    lines = [
        f"# Model/prompt qualification matrix: {report.matrix_id}",
        "",
        f"- Corpus: `{report.corpus_id}`",
        f"- Overall result: **{'PASS' if report.passed else 'FAIL'}**",
        f"- Pareto front: {', '.join(report.pareto_front) or 'none'}",
        "",
        "## Ranking",
        "",
        (
            "| Rank | Prompt | Model | Reasoning | Gold F1 | Stddev | "
            "Coverage | Time | Memory | Result |"
        ),
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    by_key = {_candidate_key(item): item for item in report.candidates}
    for rank, key in enumerate(report.ranking, start=1):
        item = by_key[key]
        model = models[item.model_id]
        duration = (
            f"{item.mean_duration_seconds:.2f}s"
            if item.mean_duration_seconds is not None
            else "n/a"
        )
        memory = f"{item.peak_memory_gb:.2f}GB" if item.peak_memory_gb is not None else "n/a"
        marker = "PASS" if item.passed else "FAIL"
        if item.pareto_optimal:
            marker += " · Pareto"
        lines.append(
            f"| {rank} | `{item.prompt_id}` | `{model.id}` | "
            f"`{item.reasoning_mode_id}` | {item.mean_gold_f1:.4f} | "
            f"{item.gold_f1_stddev:.4f} | {item.mean_gold_coverage:.4f} | "
            f"{duration} | {memory} | {marker} |"
        )
    lines.extend(["", "## Regression diagnostics", ""])
    failures = [item for item in report.candidates if item.regressions]
    if not failures:
        lines.append("No threshold violations were detected.")
    for item in failures:
        lines.append(f"### {item.prompt_id} / {item.model_id} / {item.reasoning_mode_id}")
        lines.extend(f"- {message}" for message in item.regressions)
        lines.append("")
    if report.diagnostics:
        lines.extend(["## Matrix diagnostics", ""])
        lines.extend(f"- {message}" for message in report.diagnostics)
    return "\n".join(lines).rstrip() + "\n"
