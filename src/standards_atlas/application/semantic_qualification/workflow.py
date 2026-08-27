"""Corpus construction and reproducible prompt/model matrix workflows."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.evaluation.models import EvaluationDataset, EvaluationRun
from standards_atlas.application.evaluation.repository import (
    EvaluationDatasetRepository,
    PromptRepository,
)
from standards_atlas.application.evaluation.runner import EvaluationRunner
from standards_atlas.application.semantic_qualification.annotations import (
    ClauseReference,
    CorpusClause,
    CorpusManifestRepository,
    CorpusPopulationStatistics,
    EvaluationCorpusManifest,
)
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseContentProfile,
    ClauseDescriptor,
    ClauseFilter,
    ClauseProvider,
    SamplingStrategy,
)
from standards_atlas.application.semantic_qualification.eligibility import (
    SemanticTaskEligibilityPolicy,
)
from standards_atlas.application.semantic_qualification.proposals import SemanticTaskRepository


class CorpusBuildConfig(BaseModel):
    """Configuration for a reproducible local clause corpus draft."""

    model_config = ConfigDict(frozen=True)

    task: str = Field(min_length=1)
    version: str = Field(min_length=1)
    count: int = Field(gt=0)
    strategy: SamplingStrategy = SamplingStrategy.BALANCED_BY_DOCUMENT
    seed: int = 0
    filters: ClauseFilter = ClauseFilter()
    include_text: bool = True
    knowledge_domain: str = "default"
    corpus_id: str | None = None
    exclude_table_dominant: bool = True
    resources: Path = Path("src/standards_atlas/resources/semantic")


class BenchmarkManifest(BaseModel):
    """Versioned definition of a complete prompt/model benchmark matrix."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, ge=1)
    task: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    prompt_versions: tuple[str, ...] = Field(min_length=1)
    models: tuple[str, ...] = Field(min_length=1)
    resources: Path = Path("src/standards_atlas/resources/semantic")
    output: Path = Path(".atlas/data/evaluation/runs")
    include_case_details: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_duplicates(self) -> BenchmarkManifest:
        if len(set(self.prompt_versions)) != len(self.prompt_versions):
            raise ValueError("prompt_versions must be unique")
        if len(set(self.models)) != len(self.models):
            raise ValueError("models must be unique")
        return self

    @classmethod
    def load(cls, path: Path) -> BenchmarkManifest:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(payload)

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude={"output"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CorpusBuildResult:
    dataset_path: Path
    manifest_path: Path
    clause_count: int


@dataclass(frozen=True)
class BenchmarkMatrixResult:
    manifest_hash: str
    runs: tuple[EvaluationRun, ...]


class EvaluationCorpusBuilder:
    """Build annotation-ready local corpora from a ClauseProvider."""

    def __init__(self, provider: ClauseProvider) -> None:
        self._provider = provider

    def build(self, config: CorpusBuildConfig, output_root: Path) -> CorpusBuildResult:
        total_population = self._provider.list_clauses(filters=config.filters)
        non_empty_population = tuple(clause for clause in total_population if clause.text.strip())
        policy = _eligibility_policy(config)
        table_dominant_population = tuple(
            clause for clause in non_empty_population if not policy.evaluate_clause(clause).eligible
        )
        qualification_population = (
            tuple(
                clause for clause in non_empty_population if policy.evaluate_clause(clause).eligible
            )
            if config.exclude_table_dominant
            else non_empty_population
        )
        population = _canonical_clause_occurrences(qualification_population)
        if config.count > len(population):
            exclusions = "empty clauses and duplicate occurrences"
            if config.exclude_table_dominant:
                exclusions = "empty clauses, table-dominant clauses, and duplicate occurrences"
            raise ValueError(
                f"sample count {config.count} exceeds eligible population {len(population)} "
                f"after excluding {exclusions} from composed family documents"
            )
        clauses = _sample_eligible_population(
            population, config.count, config.strategy, config.seed
        )
        clause_index = {clause.id: clause for clause in total_population}

        target = output_root / config.task / config.version
        target.mkdir(parents=True, exist_ok=True)
        examples = []
        corpus_clauses = []
        for clause in clauses:
            strata = _strata_for(clause)
            item_input: dict[str, Any] = {
                "content": {"hash": clause.content_hash},
                "context": {
                    "knowledge_domain": config.knowledge_domain,
                    "document_key": clause.document_key,
                    "clause_id": clause.id,
                    "reference": clause.clause_reference,
                    "heading": clause.heading,
                    "parent_id": clause.parent_id,
                    "ancestor_headings": _ancestor_headings(clause, clause_index),
                    "structural_roles": [role.value for role in clause.statement_functions],
                    "clause_type": clause.clause_type.value,
                    "canonical_section": (
                        clause.canonical_section.value if clause.canonical_section else None
                    ),
                    "document_categories": list(clause.document_categories),
                    "domain_categories": list(clause.domain_categories),
                    "semantic_sections": [
                        section.model_dump(mode="json") for section in clause.semantic_sections
                    ],
                    "structural_context": clause.structural_context,
                    "reference_mentions": list(clause.reference_mentions),
                    "content_profile": clause.content_profile.value,
                    "table_block_count": clause.table_block_count,
                    "eligibility": policy.evaluate_clause(clause).model_dump(mode="json"),
                },
            }
            if config.include_text:
                item_input["content"]["text"] = clause.text
            examples.append(
                {
                    "id": clause.id,
                    "tags": sorted(set(strata.values())),
                    "input": item_input,
                    "expected": {},
                    "annotation_status": "proposed",
                }
            )
            corpus_clauses.append(
                CorpusClause(
                    clause=ClauseReference(
                        knowledge_domain=config.knowledge_domain,
                        document_key=clause.document_key,
                        clause_id=clause.id,
                        content_hash=clause.content_hash,
                    ),
                    strata=strata,
                )
            )

        corpus_id = config.corpus_id or f"{config.task}-{config.version}"
        manifest = EvaluationCorpusManifest(
            corpus_id=corpus_id,
            task=config.task,
            corpus_version=config.version,
            selection_strategy=config.strategy.value,
            seed=config.seed,
            filters=config.filters.model_dump(mode="json"),
            statistics=_statistics(
                total_population,
                non_empty_population,
                qualification_population,
                population,
                clauses,
            ),
            duplicate_content_groups=_duplicate_content_groups(clauses),
            exclusions=(
                {
                    "table_dominant": tuple(
                        _readable_clause_occurrence(clause) for clause in table_dominant_population
                    )
                }
                if config.exclude_table_dominant and table_dominant_population
                else {}
            ),
            clauses=tuple(corpus_clauses),
        )
        dataset_path = target / "dataset.json"
        dataset_path.write_text(
            json.dumps(
                {"task": config.task, "version": config.version, "examples": examples},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_path = CorpusManifestRepository(output_root).write(manifest)
        return CorpusBuildResult(dataset_path, manifest_path, len(clauses))


class EvaluationMatrixRunner:
    """Execute every prompt/model combination declared by a manifest."""

    def __init__(self, runner: EvaluationRunner) -> None:
        self._runner = runner

    def run(self, manifest: BenchmarkManifest) -> BenchmarkMatrixResult:
        prompts = PromptRepository(manifest.resources / "prompts")
        dataset: EvaluationDataset = EvaluationDatasetRepository(
            manifest.resources / "corpora"
        ).load(manifest.task, manifest.dataset_version)
        runs = tuple(
            self._runner.run(
                prompts.load(manifest.task, prompt_version),
                dataset,
                model=model,
            )
            for prompt_version in manifest.prompt_versions
            for model in manifest.models
        )
        manifest_hash = manifest.fingerprint()
        enriched = tuple(
            EvaluationRun(
                task=run.task,
                prompt_version=run.prompt_version,
                dataset_version=run.dataset_version,
                model=run.model,
                provider=run.provider,
                metrics=run.metrics,
                cases=run.cases,
                metadata={
                    **dict(run.metadata),
                    **manifest.metadata,
                    "benchmark_manifest_hash": manifest_hash,
                },
            )
            for run in runs
        )
        return BenchmarkMatrixResult(manifest_hash, enriched)


def _ancestor_headings(
    clause: ClauseDescriptor, clause_index: dict[str, ClauseDescriptor]
) -> list[dict[str, str]]:
    """Return nearest-first titled ancestors without crossing document boundaries."""

    headings: list[dict[str, str]] = []
    seen: set[str] = set()
    parent_id = clause.parent_id
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = clause_index.get(parent_id)
        if parent is None or parent.document_key != clause.document_key:
            break
        if parent.heading and parent.heading.strip():
            headings.append(
                {
                    "clause_id": parent.id,
                    "reference": parent.clause_reference,
                    "heading": parent.heading.strip(),
                }
            )
        parent_id = parent.parent_id
    return headings


def _eligibility_policy(config: CorpusBuildConfig) -> SemanticTaskEligibilityPolicy:
    try:
        task, _ = SemanticTaskRepository(config.resources / "tasks").load(
            config.task, config.version
        )
    except (FileNotFoundError, ValueError):
        excluded = (ClauseContentProfile.TABLE_DOMINANT,) if config.exclude_table_dominant else ()
        return SemanticTaskEligibilityPolicy(excluded_content_profiles=excluded)
    return SemanticTaskEligibilityPolicy.from_task(task)


def _strata_for(clause: ClauseDescriptor) -> dict[str, str]:
    roles = "+".join(sorted(role.value for role in clause.statement_functions)) or "unknown"
    return {
        "document": clause.document_key,
        "clause_type": clause.clause_type.value,
        "structural_role": roles,
        "hierarchy_depth": str(_reference_depth(clause.clause_reference)),
        "length_class": _length_class(len(clause.text)),
        "title_presence": "titled" if clause.heading else "untitled",
    }


def _reference_depth(reference: str) -> int:
    normalized = reference.strip().strip(".")
    if not normalized:
        return 0
    return max(1, len([part for part in normalized.replace("-", ".").split(".") if part]))


def _length_class(length: int) -> str:
    if length < 200:
        return "short"
    if length < 800:
        return "medium"
    return "long"


def _sample_eligible_population(
    population: tuple[ClauseDescriptor, ...],
    count: int,
    strategy: SamplingStrategy,
    seed: int,
) -> tuple[ClauseDescriptor, ...]:
    if strategy is SamplingStrategy.REPRESENTATIVE_STRATIFIED:
        return _representative_sample(population, count, seed)

    rng = random.Random(seed)
    if strategy is SamplingStrategy.RANDOM:
        return tuple(rng.sample(population, count))
    if strategy is SamplingStrategy.BALANCED_BY_DOCUMENT:
        buckets: dict[str, list[ClauseDescriptor]] = {}
        for clause in population:
            buckets.setdefault(clause.document_key, []).append(clause)
        for bucket in buckets.values():
            rng.shuffle(bucket)
        selected: list[ClauseDescriptor] = []
        while len(selected) < count:
            progressed = False
            for document_key in sorted(buckets):
                if buckets[document_key] and len(selected) < count:
                    selected.append(buckets[document_key].pop())
                    progressed = True
            if not progressed:
                break
        return tuple(selected)
    raise ValueError(f"Unsupported sampling strategy: {strategy}")


def _representative_sample(
    population: tuple[ClauseDescriptor, ...], count: int, seed: int
) -> tuple[ClauseDescriptor, ...]:
    """Greedily cover rare strata while keeping deterministic seeded tie-breaking."""
    rng = random.Random(seed)
    candidates = list(population)
    rng.shuffle(candidates)
    frequencies: Counter[tuple[str, str]] = Counter()
    for clause in candidates:
        frequencies.update(_strata_for(clause).items())

    covered: Counter[tuple[str, str]] = Counter()
    selected: list[ClauseDescriptor] = []
    while len(selected) < count:

        def score(clause: ClauseDescriptor) -> tuple[float, float]:
            pairs = tuple(_strata_for(clause).items())
            novelty = sum(1.0 / (1 + covered[pair]) for pair in pairs)
            rarity = sum(1.0 / frequencies[pair] for pair in pairs)
            return novelty, rarity

        best = max(candidates, key=score)
        candidates.remove(best)
        selected.append(best)
        covered.update(_strata_for(best).items())
    return tuple(selected)


def _statistics(
    total_population: tuple[ClauseDescriptor, ...],
    non_empty_population: tuple[ClauseDescriptor, ...],
    qualification_population: tuple[ClauseDescriptor, ...],
    eligible_population: tuple[ClauseDescriptor, ...],
    selected: tuple[ClauseDescriptor, ...],
) -> CorpusPopulationStatistics:
    def counts(items: tuple[ClauseDescriptor, ...]) -> dict[str, dict[str, int]]:
        dimensions: dict[str, Counter[str]] = {}
        for clause in items:
            for dimension, value in _strata_for(clause).items():
                dimensions.setdefault(dimension, Counter())[value] += 1
        return {
            dimension: dict(sorted(values.items()))
            for dimension, values in sorted(dimensions.items())
        }

    return CorpusPopulationStatistics(
        total_occurrences=len(total_population),
        ineligible_empty_content=len(total_population) - len(non_empty_population),
        ineligible_table_dominant_content=(
            len(non_empty_population) - len(qualification_population)
        ),
        duplicate_document_occurrences=(len(qualification_population) - len(eligible_population)),
        eligible_occurrences=len(eligible_population),
        unique_contents=len({clause.content_hash for clause in eligible_population}),
        selected_occurrences=len(selected),
        selected_unique_contents=len({clause.content_hash for clause in selected}),
        dimensions=counts(eligible_population),
        selected_dimensions=counts(selected),
    )


def _canonical_clause_occurrences(
    clauses: tuple[ClauseDescriptor, ...],
) -> tuple[ClauseDescriptor, ...]:
    """Legacy safeguard against obsolete persisted family-document copies.

    Current workflows keep composed publication views below ``.atlas/work`` and
    corpus providers therefore see only canonical physical documents. The
    deduplication remains temporarily to protect workspaces created by older
    versions that still contain ``.atlas/data/documents/<family>.json``.
    """
    document_sizes = Counter(clause.document_key for clause in clauses)
    canonical: dict[tuple[str, str], ClauseDescriptor] = {}
    for clause in clauses:
        occurrence_key = (clause.id, clause.content_hash)
        current = canonical.get(occurrence_key)
        if current is None:
            canonical[occurrence_key] = clause
            continue
        candidate_rank = (document_sizes[clause.document_key], clause.document_key)
        current_rank = (document_sizes[current.document_key], current.document_key)
        if candidate_rank < current_rank:
            canonical[occurrence_key] = clause
    return tuple(
        sorted(
            canonical.values(),
            key=lambda clause: (clause.document_key, clause.clause_reference, clause.id),
        )
    )


def _readable_clause_occurrence(clause: ClauseDescriptor) -> str:
    reference = clause.clause_reference.strip() or clause.reference.strip()
    title = clause.heading.strip() if clause.heading else ""
    label = f"{clause.document_key}:{reference}"
    if title:
        label += f" — {title}"
    return f"{label} [{clause.id}]"


def _duplicate_content_groups(
    clauses: tuple[ClauseDescriptor, ...],
) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for clause in clauses:
        groups.setdefault(clause.content_hash, []).append(_readable_clause_occurrence(clause))
    return {
        content_hash: tuple(sorted(references))
        for content_hash, references in sorted(groups.items())
        if len(references) > 1
    }
