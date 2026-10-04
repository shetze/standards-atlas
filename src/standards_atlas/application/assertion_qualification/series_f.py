"""AP03 Series-F preparation for B0 and controlled Development prompt comparisons."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.assertion_qualification.experiment import (
    AssertionExperimentManifest,
    ExperimentBudget,
    manifest_sha256,
)
from standards_atlas.application.assertion_qualification.models import AssertionGoldenPartition
from standards_atlas.application.schema.model import SchemaBoundModel

AP03_SERIES_F_PLAN_CONTRACT = "ap03-series-f-development-plan-v1"
AP03_SERIES_F_PLAN_SCHEMA_VERSION = 1

SERIES_F_PROMPTS: Mapping[str, str] = {
    "B0-AP02": "ontology-guided-assertions-source-bound-v1",
    "P1": "engineering-policy-v1",
    "P2": "engineering-policy-contrast-v1",
}


class SeriesFExperimentRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: str = Field(min_length=1)
    variant_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: int = Field(ge=1)
    repetitions: int = Field(ge=1)
    conservative_call_upper_bound: int = Field(ge=1)
    execution_authorized: bool


class SeriesFDevelopmentPlan(SchemaBoundModel):
    """Text-safe run order. It references private manifests but carries no source text."""

    SCHEMA_FAMILY: ClassVar[str] = "ap03-series-f-development-plan"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = AP03_SERIES_F_PLAN_SCHEMA_VERSION
    contract_id: str = AP03_SERIES_F_PLAN_CONTRACT
    campaign_id: str = Field(min_length=1)
    partition: str = "development"
    golden_suite_id: str = Field(min_length=1)
    golden_suite_version: str = Field(min_length=1)
    golden_suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_revision: str = Field(min_length=1)
    runtime_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_route: str = Field(min_length=1)
    requested_model: str | None = None
    authorization_reference: str | None = None
    same_factor_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiments: tuple[SeriesFExperimentRef, ...] = Field(min_length=3)
    execution_order: tuple[str, ...]
    historical_v8_required_if_available: bool = True
    holdout_access_permitted: bool = False
    automatic_knowledge_adoption: bool = False
    measured_results_present: bool = False

    @model_validator(mode="after")
    def development_only(self) -> SeriesFDevelopmentPlan:
        if self.partition != AssertionGoldenPartition.DEVELOPMENT.value:
            raise ValueError("Series F is Development-only")
        if self.holdout_access_permitted:
            raise ValueError("Series F must not permit Holdout access")
        if self.automatic_knowledge_adoption:
            raise ValueError("Series F must not enable automatic knowledge adoption")
        ids = {item.experiment_id for item in self.experiments}
        if tuple(self.execution_order) != tuple(item.experiment_id for item in self.experiments):
            raise ValueError("execution_order must exactly match the prepared experiment sequence")
        if len(ids) != len(self.experiments):
            raise ValueError("Series-F experiment ids must be unique")
        return self


def same_factor_fingerprint(manifest: AssertionExperimentManifest) -> str:
    """Hash factors that must remain identical for the controlled prompt comparison."""

    payload = {
        "code_revision": manifest.code_revision,
        "partition": manifest.partition,
        "golden_suite_id": manifest.golden_suite_id,
        "golden_suite_version": manifest.golden_suite_version,
        "golden_suite_sha256": manifest.golden_suite_sha256,
        "ontology_versions": manifest.ontology_versions,
        "task_schema_version": manifest.task_schema_version,
        "data_route": manifest.data_route,
        "privacy_classification": manifest.privacy_classification,
        "model_route": manifest.model_route,
        "runtime_config_sha256": manifest.runtime_config_sha256,
        "requested_model": manifest.requested_model,
        "temperature": manifest.temperature,
        "seed": manifest.seed,
        "max_output_tokens_per_call": manifest.max_output_tokens_per_call,
        "reasoning_enabled": manifest.reasoning_enabled,
        "repetitions": manifest.repetitions,
        "bypass_cache_for_repetitions": manifest.bypass_cache_for_repetitions,
        "enabled_call_kinds": manifest.enabled_call_kinds,
        "budget": manifest.budget.model_dump(mode="json"),
        "case_source_packages": [
            {
                "document_key": case.document_key,
                "clause_id": case.clause_id,
                "source_package_binding": case.source_package_binding.model_dump(mode="json"),
            }
            for case in manifest.cases
        ],
    }
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_series_f_smoke_manifest(
    full_b0_manifest: AssertionExperimentManifest,
    *,
    experiment_id: str,
    smoke_cases: int,
    budget: ExperimentBudget,
) -> AssertionExperimentManifest:
    """Create a B0 smoke subset while retaining the full Development-suite binding."""

    if full_b0_manifest.partition != AssertionGoldenPartition.DEVELOPMENT.value:
        raise ValueError("Series-F smoke accepts only a Development manifest")
    if full_b0_manifest.variant_id != "B0-AP02":
        raise ValueError("Series-F smoke must be derived from the full B0 manifest")
    if smoke_cases < 1 or smoke_cases >= len(full_b0_manifest.cases):
        raise ValueError("Series-F smoke must be a strict non-empty subset of full B0")

    payload = full_b0_manifest.model_dump(mode="json")
    payload.update(
        {
            "experiment_id": experiment_id,
            "cases": [
                case.model_dump(mode="json") for case in full_b0_manifest.cases[:smoke_cases]
            ],
            "conservative_call_upper_bound": (
                smoke_cases * full_b0_manifest.repetitions * (1 + budget.max_retries_per_case)
            ),
            "budget": budget.model_dump(mode="json"),
        }
    )
    return AssertionExperimentManifest.model_validate(payload)


def build_series_f_plan(
    *,
    campaign_id: str,
    full_manifests: tuple[AssertionExperimentManifest, ...],
    smoke_manifest: AssertionExperimentManifest | None = None,
) -> SeriesFDevelopmentPlan:
    if not full_manifests:
        raise ValueError("Series F requires prepared Development manifests")
    first = full_manifests[0]
    if first.partition != AssertionGoldenPartition.DEVELOPMENT.value:
        raise ValueError("Series F accepts only a Development golden suite")
    expected_variants = tuple(SERIES_F_PROMPTS)
    actual_variants = tuple(item.variant_id for item in full_manifests)
    if actual_variants != expected_variants:
        raise ValueError(
            f"Series F variants must be {expected_variants!r} in order, got {actual_variants!r}"
        )
    fingerprints = {same_factor_fingerprint(item) for item in full_manifests}
    if len(fingerprints) != 1:
        raise ValueError("B0/P1/P2 do not keep all non-prompt factors identical")
    fingerprint = next(iter(fingerprints))

    refs: list[SeriesFExperimentRef] = []
    if smoke_manifest is not None:
        if smoke_manifest.partition != first.partition or smoke_manifest.variant_id != "B0-AP02":
            raise ValueError("Series-F smoke must be a B0 Development experiment")
        if smoke_manifest.prompt_version != SERIES_F_PROMPTS["B0-AP02"]:
            raise ValueError("Series-F smoke must use the frozen B0 prompt")
        if len(smoke_manifest.cases) >= len(first.cases):
            raise ValueError("B0 smoke must be a strict subset of the full Development run")
        refs.append(_experiment_ref(smoke_manifest, role="b0_smoke"))
    refs.extend(
        _experiment_ref(item, role="b0_full" if item.variant_id == "B0-AP02" else "variant")
        for item in full_manifests
    )
    return SeriesFDevelopmentPlan(
        campaign_id=campaign_id,
        golden_suite_id=first.golden_suite_id,
        golden_suite_version=first.golden_suite_version,
        golden_suite_sha256=first.golden_suite_sha256,
        code_revision=first.code_revision,
        runtime_config_sha256=first.runtime_config_sha256 or "0" * 64,
        model_route=first.model_route,
        requested_model=first.requested_model,
        authorization_reference=first.authorization_reference,
        same_factor_fingerprint=fingerprint,
        experiments=tuple(refs),
        execution_order=tuple(item.experiment_id for item in refs),
    )


def _experiment_ref(manifest: AssertionExperimentManifest, *, role: str) -> SeriesFExperimentRef:
    return SeriesFExperimentRef(
        role=role,
        variant_id=manifest.variant_id,
        experiment_id=manifest.experiment_id,
        prompt_version=manifest.prompt_version,
        manifest_sha256=manifest_sha256(manifest),
        cases=len(manifest.cases),
        repetitions=manifest.repetitions,
        conservative_call_upper_bound=manifest.conservative_call_upper_bound,
        execution_authorized=manifest.execution_authorized,
    )
