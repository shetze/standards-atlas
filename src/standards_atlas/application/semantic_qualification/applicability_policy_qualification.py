"""Qualification configuration and persisted state for the applicability policy."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.applicability_decision_policy import (
    POLICY_ID,
    POLICY_MODEL_ID,
    POLICY_VERSION,
)

APPLICABILITY_POLICY_ARTIFACT_DIRECTORY = "applicability-policy"
APPLICABILITY_POLICY_RUN_FILENAME = "applicability-policy-run.json"
APPLICABILITY_POLICY_SELECTION_FILENAME = "applicability-policy-selection.json"
APPLICABILITY_POLICY_STATE_FILENAME = "applicability-policy-run-state.json"
APPLICABILITY_POLICY_EVALUATION_FILENAME = "applicability-policy-evaluation.json"


class ApplicabilityPolicyQualificationMode(StrEnum):
    """How freshness was established for one policy qualification run."""

    OPERATIONAL = "operational"
    FRESH_DETAIL_FIXED_PRESENCE = "fresh_detail_fixed_presence"
    FRESH_END_TO_END = "fresh_end_to_end"


class ApplicabilityPolicyRoleConfig(BaseModel):
    """Manifest-owned task/prompt contract for one qualified policy role."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


class ApplicabilityDecisionPolicyConfig(BaseModel):
    """Manifest-owned activation and quality budget for the qualified policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    policy_id: Literal[POLICY_ID] = POLICY_ID
    policy_version: Literal[POLICY_VERSION] = POLICY_VERSION
    model: str | None = None
    primary: ApplicabilityPolicyRoleConfig = ApplicabilityPolicyRoleConfig(
        task_version="2.0.0",
        prompt_version="detail-structure-aware-v4",
    )
    rescue: ApplicabilityPolicyRoleConfig = ApplicabilityPolicyRoleConfig(
        task_version="2.0.0",
        prompt_version="detail-structure-aware-v3",
    )
    confirmation: ApplicabilityPolicyRoleConfig = ApplicabilityPolicyRoleConfig(
        task_version="1.0.0",
        prompt_version="detail-structure-aware-v1",
    )
    golden_corpus: Path | None = None
    max_false_positive: int = Field(default=2, ge=0)
    max_false_negative: int = Field(default=2, ge=0)
    required_fresh_repetitions: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def validate_qualified_contract(self) -> ApplicabilityDecisionPolicyConfig:
        if not self.enabled:
            return self
        if self.model is None:
            raise ValueError("enabled applicability decision policy requires a model")
        if self.model != POLICY_MODEL_ID:
            raise ValueError(
                f"qualified applicability decision policy requires model {POLICY_MODEL_ID!r}"
            )
        expected = {
            "primary": ("2.0.0", "detail-structure-aware-v4"),
            "rescue": ("2.0.0", "detail-structure-aware-v3"),
            "confirmation": ("1.0.0", "detail-structure-aware-v1"),
        }
        configured = {
            "primary": (self.primary.task_version, self.primary.prompt_version),
            "rescue": (self.rescue.task_version, self.rescue.prompt_version),
            "confirmation": (
                self.confirmation.task_version,
                self.confirmation.prompt_version,
            ),
        }
        if configured != expected:
            raise ValueError(
                "applicability decision policy role contracts differ from the "
                f"qualified {POLICY_ID} {POLICY_VERSION} contract"
            )
        return self


class ApplicabilityPolicyRunState(BaseModel):
    """Persistent execution state shared by fresh and resumed policy invocations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0", "1.1"] = "1.1"
    policy_id: Literal[POLICY_ID] = POLICY_ID
    policy_version: Literal[POLICY_VERSION] = POLICY_VERSION
    source_selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_id: str = Field(min_length=1)
    model_ref: str = Field(min_length=1)
    cache_disabled: bool = False
    fresh_requested: bool = False
    qualification_mode: ApplicabilityPolicyQualificationMode = (
        ApplicabilityPolicyQualificationMode.OPERATIONAL
    )
