"""Experimental partial observations: absence is not a semantic negative.

These contracts deliberately do not inherit StatementFunctionSelection. That
legacy full-answer model materializes defaults and is not a partial observer.
No conversion to ModelVote or published enrichment exists before Slice 5.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification.annotations import ClauseReference
from standards_atlas.application.semantic_qualification.taxonomy_decisions import (
    DECISION_ATTRIBUTES,
    ClauseDecisionPlan,
    DecisionAttribute,
)

# Current presence/tuple contract: never reintroduce legacy scalar role types.
PARTIAL_ATTRIBUTES: tuple[DecisionAttribute, ...] = tuple(
    key for key in DECISION_ATTRIBUTES if key != "role_relation_types"
)
PRIMARY_SET_FIELDS = (
    ("primary_function", "statement_functions"),
    ("primary_knowledge_kind", "knowledge_kinds"),
    ("primary_process_function", "process_functions"),
)
PARTIAL_TASK = "semantic-attribute-observation"
PARTIAL_TASK_VERSION = "1.0.0"
PARTIAL_PROMPT = "taxonomy-partial-v1"


def ordered_attributes(values: tuple[str, ...] | list[str]) -> tuple[DecisionAttribute, ...]:
    """Validate the current task contract, with canonical order and no duplicates."""
    if len(values) != len(set(values)) or set(values) - set(PARTIAL_ATTRIBUTES):
        raise ValueError("partial attributes must be unique current semantic attribute names")
    return tuple(name for name in PARTIAL_ATTRIBUTES if name in values)


class PartialRequestPlan(BaseModel):
    """An explicit, source-bound question plan; fixed values are NOT observations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    experimental_only: Literal[True] = True
    task: Literal["semantic-attribute-observation"] = PARTIAL_TASK
    task_version: Literal["1.0.0"] = PARTIAL_TASK_VERSION
    clause: ClauseReference
    decision_plan: ClauseDecisionPlan
    selected_attributes: tuple[DecisionAttribute, ...]
    requested_attributes: tuple[DecisionAttribute, ...]
    fixed_attributes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def source_and_partition(self) -> PartialRequestPlan:
        source = self.decision_plan.source
        if (source.document_key, source.clause_id, source.content_hash) != (
            self.clause.document_key,
            self.clause.clause_id,
            self.clause.content_hash,
        ):
            raise ValueError("partial plan and clause source identities differ")
        for attributes in (self.selected_attributes, self.requested_attributes):
            if ordered_attributes(attributes) != attributes:
                raise ValueError("partial attributes must use canonical order")
        fixed = {
            key: self.decision_plan.decision(key).value
            for key in self.selected_attributes
            if self.decision_plan.decision(key).state == "fixed"
        }
        if self.fixed_attributes != fixed:
            raise ValueError("fixed attributes must be exactly the selected source predecisions")
        if self.requested_attributes != tuple(
            key for key in self.selected_attributes if key not in fixed
        ):
            raise ValueError("selected attributes must partition into fixed and requested")
        return self

    @property
    def fingerprint(self) -> str:
        return structure_fingerprint(self.model_dump(mode="json"))

    @property
    def fixed_primary_constraints(self) -> dict[str, str]:
        """Only bind an open set to its fixed primary; never expose unrelated targets."""
        return {
            primary: decision.value
            for primary, collection in PRIMARY_SET_FIELDS
            if collection in self.requested_attributes
            and (decision := self.decision_plan.decision(primary)).state == "fixed"
        }

    @property
    def request_count(self) -> int:
        return int(bool(self.requested_attributes))


class AttributeObservationState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attribute: DecisionAttribute
    status: Literal["evaluated", "not_requested", "failed"]
    reason: Literal["model_response", "fixed", "outside_selection", "request_failed"]


class PartialObservation(BaseModel):
    """One logical model observation, regardless of retries, cache or resumption."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0"] = "1.0"
    experimental_only: Literal[True] = True
    plan: PartialRequestPlan
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    outcome: Literal["evaluated", "failed", "not_requested"]
    states: tuple[AttributeObservationState, ...]
    # Exact successful response keys, including optional response metadata. No defaults.
    values: dict[str, Any] = Field(default_factory=dict)
    provided_fields: tuple[str, ...] = ()
    response_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    error: str | None = None

    @model_validator(mode="after")
    def observation_is_explicit(self) -> PartialObservation:
        if tuple(item.attribute for item in self.states) != PARTIAL_ATTRIBUTES:
            raise ValueError("observation must account for every current task attribute once")
        if self.provided_fields != tuple(sorted(set(self.provided_fields))):
            raise ValueError("provided fields must be unique and sorted")
        requested = set(self.plan.requested_attributes)
        if (self.outcome == "not_requested") != (not requested):
            raise ValueError("only empty question plans have not_requested outcomes")
        for state in self.states:
            if state.attribute in requested:
                expected = (
                    self.outcome,
                    "model_response" if self.outcome == "evaluated" else "request_failed",
                )
            else:
                expected = (
                    "not_requested",
                    (
                        "fixed"
                        if state.attribute in self.plan.fixed_attributes
                        else "outside_selection"
                    ),
                )
            if (state.status, state.reason) != expected:
                raise ValueError("attribute states disagree with request plan and outcome")
        if self.outcome == "evaluated":
            if self.error or not requested.issubset(self.values):
                raise ValueError("successful observations require all requested values")
            if set(self.values) - requested - {"confidence", "rationale"}:
                raise ValueError("unrequested attributes are not model observations")
            if self.provided_fields != tuple(sorted(self.values)) or not self.response_sha256:
                raise ValueError("successful observations need exact provided fields and response")
        elif self.values:
            raise ValueError("failed or unrequested answers must not materialize semantic values")
        if (self.outcome == "failed") != (self.error is not None):
            raise ValueError("only failed observations carry an error")
        if self.outcome == "not_requested" and (self.provided_fields or self.response_sha256):
            raise ValueError("no-request outcome cannot claim response evidence")
        return self

    @property
    def voter_key(self) -> str:
        return f"{self.provider}:{self.model}"

    @property
    def observation_id(self) -> str:
        return structure_fingerprint(
            {
                "clause": self.plan.clause.model_dump(mode="json"),
                "voter": self.voter_key,
                "request": self.request_fingerprint,
            }
        )

    def model_evidence(self) -> dict[str, Any]:
        """Sparse evidence only; zero entries for unasked or unsuccessful attributes."""
        if self.outcome != "evaluated":
            return {}
        return {key: self.values[key] for key in self.plan.requested_attributes}


def observation_states(
    plan: PartialRequestPlan, outcome: Literal["evaluated", "failed", "not_requested"]
) -> tuple[AttributeObservationState, ...]:
    return tuple(
        AttributeObservationState(
            attribute=key,
            status=outcome if key in plan.requested_attributes else "not_requested",
            reason=("model_response" if outcome == "evaluated" else "request_failed")
            if key in plan.requested_attributes
            else ("fixed" if key in plan.fixed_attributes else "outside_selection"),
        )
        for key in PARTIAL_ATTRIBUTES
    )


def validate_partial_response(
    value: Mapping[str, Any], schema: Mapping[str, Any], plan: PartialRequestPlan
) -> dict[str, Any]:
    """Validate without coercion, deduplication, defaulting or invented set members.

    A malformed grouped answer fails the group. Salvaging partial provider output
    would need a separately qualified contract; it is not silently done here.
    """
    candidate = dict(value)
    errors = sorted(Draft202012Validator(schema).iter_errors(candidate), key=lambda e: e.message)
    if errors:
        raise ValueError(f"partial response violates request schema: {errors[0].message}")
    for primary, collection in PRIMARY_SET_FIELDS:
        primary_value = candidate.get(primary, plan.fixed_primary_constraints.get(primary))
        if collection in candidate and primary_value is not None:
            if primary_value not in candidate[collection]:
                raise ValueError(f"{primary} must belong to the explicitly evaluated {collection}")
    if candidate.get("role_semantics_present") is False and candidate.get("role_relations"):
        raise ValueError("nonempty role_relations conflict with evaluated negative role presence")
    return candidate
