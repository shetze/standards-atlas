"""Corpus construction and reproducible prompt/model matrix workflows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.services.evaluation.clause_access import (
    ClauseFilter,
    ClauseProvider,
    SamplingStrategy,
)
from standards_atlas.application.services.evaluation.models import EvaluationDataset, EvaluationRun
from standards_atlas.application.services.evaluation.repository import (
    EvaluationDatasetRepository,
    PromptRepository,
)
from standards_atlas.application.services.evaluation.runner import EvaluationRunner


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


class BenchmarkManifest(BaseModel):
    """Versioned definition of a complete prompt/model benchmark matrix."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, ge=1)
    task: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    prompt_versions: tuple[str, ...] = Field(min_length=1)
    models: tuple[str, ...] = Field(min_length=1)
    resources: Path = Path("src/standards_atlas/resources/semantic")
    output: Path = Path(".atlas/evaluation/runs")
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
        clauses = self._provider.sample_clauses(
            count=config.count,
            strategy=config.strategy,
            filters=config.filters,
            seed=config.seed,
        )
        target = output_root / config.task / config.version
        target.mkdir(parents=True, exist_ok=True)
        examples = []
        sources = []
        for clause in clauses:
            item_input: dict[str, Any] = {
                "reference": clause.clause_reference,
                "document_key": clause.document_key,
                "clause_id": clause.id,
                "clause_hash": clause.clause_hash,
            }
            if config.include_text:
                item_input["text"] = clause.text
            examples.append(
                {
                    "id": clause.id,
                    "tags": [
                        clause.clause_type.value,
                        *[role.value for role in clause.semantic_roles],
                    ],
                    "input": item_input,
                    "expected": {},
                    "annotation_status": "proposed",
                }
            )
            sources.append({"clause_id": clause.id, "clause_hash": clause.clause_hash})
        dataset = {
            "task": config.task,
            "version": config.version,
            "examples": examples,
        }
        manifest = {
            "schema_version": 1,
            "task": config.task,
            "version": config.version,
            "count": len(clauses),
            "strategy": config.strategy.value,
            "seed": config.seed,
            "filters": config.filters.model_dump(mode="json"),
            "contains_clause_text": config.include_text,
            "sources": sources,
        }
        dataset_path = target / "dataset.json"
        manifest_path = target / "corpus-manifest.json"
        dataset_path.write_text(
            json.dumps(dataset, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
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
