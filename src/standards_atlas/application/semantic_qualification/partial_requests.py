"""Versioned experimental question planning, using the existing request builder."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import ConfigDict, field_validator, model_validator

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.ports.llm_gateway import StructuredGenerationRequest
from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_ATTRIBUTES,
    PARTIAL_PROMPT,
    PARTIAL_TASK,
    PARTIAL_TASK_VERSION,
    PartialRequestPlan,
    ordered_attributes,
)
from standards_atlas.application.semantic_qualification.proposals import (
    ProposalRunConfig,
    SemanticTaskDefinition,
    SemanticTaskRepository,
)
from standards_atlas.application.semantic_qualification.request_builder import (
    build_clause_reference,
    build_proposal_request,
)
from standards_atlas.application.semantic_qualification.taxonomy_decisions import (
    DecisionAttribute,
    derive_clause_decision_plan,
)


class PartialProposalConfig(ProposalRunConfig):
    """Separate opt-in task; full-task versions cannot enter this path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: Literal["semantic-attribute-observation"] = PARTIAL_TASK
    task_version: Literal["1.0.0"] = PARTIAL_TASK_VERSION
    prompt_version: Literal["taxonomy-partial-v1", "taxonomy-partial-v2"] = PARTIAL_PROMPT
    cbox_frame: Literal["taxonomy-grounded-v1"] = "taxonomy-grounded-v1"
    adaptive_interview: Literal[False] = False
    overwrite: Literal[False] = False
    selected_attributes: tuple[DecisionAttribute, ...] = PARTIAL_ATTRIBUTES

    @field_validator("selected_attributes")
    @classmethod
    def current_attributes(cls, value):
        return ordered_attributes(value)

    @model_validator(mode="after")
    def no_legacy_execution_options(self) -> PartialProposalConfig:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("partial provider and model identities must not be blank")
        if self.adaptive_question_max_tokens is not None:
            raise ValueError("partial observations do not use adaptive interview options")
        return self


@dataclass(frozen=True)
class PartialTaskResources:
    task: SemanticTaskDefinition
    prompt: PromptDefinition
    schema: Mapping[str, Any]

    @classmethod
    def load(cls, resources: Path, config: PartialProposalConfig) -> PartialTaskResources:
        task, schema = SemanticTaskRepository(resources / "tasks").load(
            config.task, config.task_version
        )
        prompt = PromptRepository(resources / "prompts").load(config.task, config.prompt_version)
        if task.task != config.task or task.version != config.task_version:
            raise ValueError("partial task resource identity mismatch")
        if prompt.output_schema != schema:
            raise ValueError("partial prompt and canonical task schemas must match")
        expected_fields = set(PARTIAL_ATTRIBUTES) | {"confidence", "rationale"}
        if set(schema.get("properties", ())) != expected_fields:
            raise ValueError("partial resource does not implement the current attribute contract")
        if schema.get("additionalProperties") is not False or schema.get("required"):
            raise ValueError("partial resource must be an optional closed attribute envelope")
        Draft202012Validator.check_schema(schema)
        return cls(task, prompt, schema)


@dataclass(frozen=True)
class PreparedPartialRequest:
    example_id: str
    plan: PartialRequestPlan
    request: StructuredGenerationRequest | None
    fingerprint: str


def prepare_partial_request(
    config: PartialProposalConfig,
    example_id: str,
    item_input: Mapping[str, Any],
    resources: PartialTaskResources,
    *,
    accepted_attributes: Mapping[str, Any] | None = None,
    accepted_state_sha256: str | None = None,
) -> PreparedPartialRequest:
    """Derive fresh source rules; never trust persisted target labels or caller plans."""
    clause = build_clause_reference(item_input)
    context, content = item_input["context"], item_input["content"]
    decision_plan = derive_clause_decision_plan(
        context, text=content["text"], content_hash=content["hash"]
    )
    selected = config.selected_attributes
    fixed = {
        key: decision_plan.decision(key).value
        for key in selected
        if decision_plan.decision(key).state == "fixed"
    }
    accepted = {
        key: value
        for key, value in (accepted_attributes or {}).items()
        if key in selected and key not in fixed
    }
    if accepted:
        if config.prompt_version != "taxonomy-partial-v2":
            raise ValueError("carried acceptance requires taxonomy-partial-v2 prompt")
        errors = list(Draft202012Validator(resources.schema).iter_errors(accepted))
        if errors:
            raise ValueError(f"invalid carried acceptance: {errors[0].message}")
    plan = PartialRequestPlan(
        schema_version="1.1" if config.prompt_version == "taxonomy-partial-v2" else "1.0",
        clause=clause,
        decision_plan=decision_plan,
        selected_attributes=selected,
        requested_attributes=tuple(
            key for key in selected if key not in fixed and key not in accepted
        ),
        fixed_attributes=fixed,
        accepted_attributes=accepted,
        accepted_state_sha256=accepted_state_sha256,
    )
    identity = {
        "contract": "qualification-partial-input-v1",
        "plan": plan.fingerprint,
        "task": resources.task.model_dump(mode="json"),
        "prompt": {
            "version": config.prompt_version,
            "system": resources.prompt.system_prompt,
            "template": resources.prompt.user_template,
            "schema": dict(resources.schema),
        },
        "generation": config.model_dump(
            mode="json",
            exclude={
                "limit",
                "overwrite",
                "include_example_ids",
            },
        ),
    }
    if not plan.requested_attributes:
        # No compatibility fallback, and no synthetic complete-answer proposal.
        return PreparedPartialRequest(example_id, plan, None, structure_fingerprint(identity))
    schema = copy.deepcopy(dict(resources.schema))
    schema["properties"] = {
        key: value
        for key, value in schema["properties"].items()
        if key in plan.requested_attributes or key in {"confidence", "rationale"}
    }
    schema["required"] = list(plan.requested_attributes)
    request = build_proposal_request(
        config,
        replace(resources.prompt, output_schema=schema),
        item_input,
        resources.task,
        extra_template_values={
            "requested_attributes": json.dumps(list(plan.requested_attributes)),
            "fixed_primary_constraints": json.dumps(plan.fixed_primary_constraints, sort_keys=True),
            "accepted_attribute_constraints": json.dumps(plan.accepted_attributes, sort_keys=True),
        },
    )
    identity["base_input"] = request.metadata["qualification_input_fingerprint"]
    fingerprint = structure_fingerprint(identity)
    metadata = {key: value for key, value in request.metadata.items() if key != "clause_context"}
    metadata.update(
        {
            "qualification_input_fingerprint": fingerprint,
            "experimental_only": True,
            "partial_plan_fingerprint": plan.fingerprint,
            "requested_attributes": list(plan.requested_attributes),
            "source_fingerprint": plan.decision_plan.source_sha256,
            "rule_profile_fingerprint": plan.decision_plan.rules_sha256,
        }
    )
    return PreparedPartialRequest(
        example_id, plan, replace(request, metadata=metadata), fingerprint
    )
