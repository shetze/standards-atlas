"""Controlled AP03 Codex optimization handoff.

Codex may propose one small extractor role-prompt change against an already registered
Development experiment. Atlas owns validation, path selection, task/schema binding and the staged
prompt bundle.
This module never invokes an LLM and never edits Golden data, evaluators or experiment manifests.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CODEX_OPTIMIZATION_PROPOSAL_CONTRACT = "ap03-codex-prompt-proposal-v1"
CODEX_OPTIMIZATION_RECEIPT_CONTRACT = "ap03-codex-prompt-staging-v1"
KNOWLEDGE_PROPOSAL_TASK = "formal-semantic-knowledge-proposal"


def _safe_component(value: str, *, label: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or not value.replace("-", "").replace("_", "").replace(".", "").isalnum()
    ):
        raise ValueError(f"{label} must be a safe path component")
    return value


class CodexDiagnosticCluster(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=1000)
    case_ids: tuple[str, ...] = Field(min_length=1, max_length=20)


class CodexRolePromptChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["replace_role_system_prompt"] = "replace_role_system_prompt"
    system_prompt: str = Field(min_length=1)


class CodexOptimizationProposal(BaseModel):
    """Narrow client output; forbidden fields cannot smuggle plan/evaluator changes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: Literal["ap03-codex-prompt-proposal-v1"] = CODEX_OPTIMIZATION_PROPOSAL_CONTRACT
    request_id: str = Field(min_length=1, max_length=120)
    base_experiment_id: str = Field(min_length=1, max_length=120)
    base_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_prompt_task: Literal["formal-semantic-knowledge-proposal"] = KNOWLEDGE_PROPOSAL_TASK
    base_prompt_version: str = Field(min_length=1, max_length=120)
    proposed_prompt_version: str = Field(pattern=r"^codex-[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
    proposed_variant_id: str = Field(min_length=1, max_length=120)
    hypothesis: str = Field(min_length=1, max_length=2000)
    error_clusters: tuple[CodexDiagnosticCluster, ...] = Field(min_length=1, max_length=3)
    data_route: str = Field(min_length=1, max_length=200)
    change: CodexRolePromptChange

    @model_validator(mode="after")
    def validate_identity(self) -> CodexOptimizationProposal:
        _safe_component(self.request_id, label="request_id")
        _safe_component(self.base_experiment_id, label="base_experiment_id")
        _safe_component(self.base_prompt_version, label="base_prompt_version")
        _safe_component(self.proposed_prompt_version, label="proposed_prompt_version")
        _safe_component(self.proposed_variant_id, label="proposed_variant_id")
        if self.proposed_prompt_version == self.base_prompt_version:
            raise ValueError("Codex proposal must create a new prompt version")
        return self


class CodexOptimizationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: Literal["ap03-codex-prompt-staging-v1"] = CODEX_OPTIMIZATION_RECEIPT_CONTRACT
    request_id: str
    proposal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_experiment_id: str
    base_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_prompt_version: str
    proposed_prompt_version: str
    proposed_variant_id: str
    staged_bundle_relative_path: str
    staged_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    inherited_partition: str
    inherited_data_route: str
    inherited_model_route: str
    inherited_budget: dict[str, object]
    execution_performed: bool = False
    allowed_next_operations: tuple[str, ...] = (
        "assertion-experiment-plan",
        "assertion-experiment-run",
        "assertion-experiment-resume",
        "assertion-experiment-report",
    )
