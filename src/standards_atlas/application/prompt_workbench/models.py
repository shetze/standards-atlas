"""Immutable application models for prompt-workbench experiments."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.context.input_binding import ContextSourcePackage
from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.ports.knowledge_proposals import ClauseKnowledgeProposalResult
from standards_atlas.application.ports.llm_gateway import (
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from standards_atlas.application.semantic_qualification.clause_access import ClauseDescriptor


class PromptCatalogEntry(BaseModel):
    """One packaged prompt contract exposed to prompt-workbench clients."""

    model_config = ConfigDict(frozen=True)

    task: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = ""
    placeholders: tuple[str, ...] = ()
    task_schema_version: str | None = None
    qualification_status: str | None = None
    baseline_id: str | None = None
    variant_id: str | None = None
    policy_id: str | None = None
    policy_version: str | None = None
    policy_sha256: str | None = None
    example_set_id: str | None = None
    example_set_version: str | None = None
    example_set_partition: str | None = None
    example_set_sha256: str | None = None


class ModelGenerationDefaults(BaseModel):
    """Manifest-declared generation settings useful for interactive experiments."""

    model_config = ConfigDict(frozen=True)

    max_output_tokens: int | None = Field(default=None, gt=0)
    truncation_retry_max_tokens: int | None = Field(default=None, gt=0)
    reasoning_enabled: bool = False


class ModelCatalogEntry(BaseModel):
    """One selectable RamaLama model deduplicated across manifests."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    model_ref: str = Field(min_length=1)
    description: str = ""
    quantization: str | None = None
    supported_reasoning_modes: tuple[str, ...] = ("disabled",)
    generation: ModelGenerationDefaults = ModelGenerationDefaults()
    sources: tuple[str, ...] = ()


class ContextVariantDescriptor(BaseModel):
    """One versioned context projection selectable by a workbench client."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    description: str
    recommended_tasks: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssembledPromptContext:
    """Template variables plus auditable structured context projections."""

    variant: ContextVariantDescriptor
    values: Mapping[str, str]
    canonical_context: Mapping[str, Any]
    selected_context: Mapping[str, Any]
    context_text: str


@dataclass(frozen=True)
class CompiledPrompt:
    """A concrete prompt and the context facts used to render it."""

    definition: PromptDefinition
    system_prompt: str
    user_prompt: str
    output_schema: Mapping[str, Any]
    placeholders: tuple[str, ...]
    context: AssembledPromptContext


class PromptExperimentRequest(BaseModel):
    """User-controlled inputs for one reproducible structured-generation run."""

    model_config = ConfigDict(frozen=True)

    clause_identifier: str = Field(min_length=1)
    prompt_task: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    context_variant: str = "full-context-v1"
    system_prompt: str | None = None
    user_template: str | None = None
    output_schema: dict[str, Any] | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int | None = 0
    max_tokens: int | None = Field(default=None, gt=0)
    reasoning_enabled: bool | None = None
    use_cache: bool = False


@dataclass(frozen=True)
class PromptExperimentResult:
    """Structured result and provenance returned by the headless workbench."""

    clause: ClauseDescriptor
    model: ModelCatalogEntry
    compiled_prompt: CompiledPrompt
    generation_request: StructuredGenerationRequest
    generation_result: StructuredGenerationResult
    schema_valid: bool
    schema_errors: tuple[str, ...]


class SourceBoundKnowledgeExperimentRequest(BaseModel):
    """Reproducible AP03 Workbench inputs without browser-owned prompt/schema text."""

    model_config = ConfigDict(frozen=True)

    clause_identifier: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    model_id: str | None = None
    ontology_versions: tuple[str, ...] = (
        "standards-atlas-core@2.0.0",
        "functional-safety@2.1.0",
    )
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int | None = 0
    max_tokens: int | None = Field(default=None, gt=0)
    reasoning_enabled: bool | None = None
    use_cache: bool = False


@dataclass(frozen=True)
class SourceBoundKnowledgePreviewResult:
    """Model-free preview of the exact productive source package and request."""

    clause: ClauseDescriptor
    model: ModelCatalogEntry | None
    source_package: ContextSourcePackage
    interpretation_context: Mapping[str, Any]
    generation_request: StructuredGenerationRequest


@dataclass(frozen=True)
class SourceBoundKnowledgeExperimentResult:
    """Workbench run with schema, productive parser and grounding stages kept separate."""

    preview: SourceBoundKnowledgePreviewResult
    generation_result: StructuredGenerationResult
    schema_valid: bool
    schema_errors: tuple[str, ...]
    proposal_result: ClauseKnowledgeProposalResult | None
    parser_error: str | None = None
