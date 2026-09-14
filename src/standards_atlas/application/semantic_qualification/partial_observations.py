"""Experimental partial observations: absence is not a semantic negative.

These contracts deliberately do not inherit StatementFunctionSelection. That
legacy full-answer model materializes defaults and is not a partial observer.
Mixed consensus consumes these sparse records without converting them to ModelVote.
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
# Separate serialization axes: neither inherits a prompt or another family's version.
PARTIAL_REQUEST_SCHEMA_VERSION = "1.1"
PARTIAL_OBSERVATION_SCHEMA_VERSION = "1.1"


def ordered_attributes(values: tuple[str, ...] | list[str]) -> tuple[DecisionAttribute, ...]:
    """Validate the current task contract, with canonical order and no duplicates."""
    if len(values) != len(set(values)) or set(values) - set(PARTIAL_ATTRIBUTES):
        raise ValueError("partial attributes must be unique current semantic attribute names")
    return tuple(name for name in PARTIAL_ATTRIBUTES if name in values)


class PartialRequestPlan(BaseModel):
    """An explicit, source-bound question plan; fixed values are NOT observations."""

    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    schema_version: Literal["1.1"]
    experimental_only: Literal[True] = True
    task: Literal["semantic-attribute-observation"] = PARTIAL_TASK
    task_version: Literal["1.0.0"] = PARTIAL_TASK_VERSION
    clause: ClauseReference
    decision_plan: ClauseDecisionPlan
    selected_attributes: tuple[DecisionAttribute, ...]
    requested_attributes: tuple[DecisionAttribute, ...]
    fixed_attributes: dict[str, str] = Field(default_factory=dict)
    accepted_attributes: dict[str, Any] = Field(default_factory=dict)
    accepted_state_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

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
        if self.accepted_attributes and not self.accepted_state_sha256:
            raise ValueError("carried attributes need the accepting state fingerprint")
        if set(self.accepted_attributes) - set(self.selected_attributes) or (
            set(self.accepted_attributes) & set(fixed)
        ):
            raise ValueError("carried attributes must be selected, disjoint from structural fixes")
        if any(
            self.decision_plan.decision(key).state == "conflict" for key in self.accepted_attributes
        ):
            raise ValueError("a source conflict cannot inherit an accepted semantic value")
        if self.requested_attributes != tuple(
            key
            for key in self.selected_attributes
            if key not in fixed and key not in self.accepted_attributes
        ):
            raise ValueError(
                "selected attributes must partition into fixed, accepted and requested"
            )
        return self

    @property
    def fingerprint(self) -> str:
        return structure_fingerprint(self.model_dump(mode="json"))

    @property
    def fixed_primary_constraints(self) -> dict[str, str]:
        """Only bind an open set to its fixed primary; never expose unrelated targets."""
        result = {
            primary: decision.value
            for primary, collection in PRIMARY_SET_FIELDS
            if collection in self.requested_attributes
            and (decision := self.decision_plan.decision(primary)).state == "fixed"
        }
        return {
            **result,
            **{
                primary: self.accepted_attributes[primary]
                for primary, collection in PRIMARY_SET_FIELDS
                if collection in self.requested_attributes and primary in self.accepted_attributes
            },
        }

    @property
    def request_count(self) -> int:
        return int(bool(self.requested_attributes))


class AttributeObservationState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attribute: DecisionAttribute
    status: Literal["evaluated", "not_requested", "failed"]
    reason: Literal["model_response", "fixed", "accepted", "outside_selection", "request_failed"]


class PartialObservation(BaseModel):
    """One logical model observation, regardless of retries, cache or resumption."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", allow_inf_nan=False, revalidate_instances="always"
    )

    schema_version: Literal["1.1"]
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
                        else "accepted"
                        if state.attribute in self.plan.accepted_attributes
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
            else (
                "fixed"
                if key in plan.fixed_attributes
                else "accepted"
                if key in plan.accepted_attributes
                else "outside_selection"
            ),
        )
        for key in PARTIAL_ATTRIBUTES
    )


class PartialResponseIssue(BaseModel):
    """A diagnostic of original values, never an instruction to repair them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    attributes: tuple[str, ...]
    message: str
    path: tuple[str | int, ...] = ()
    observed_values: dict[str, Any] = Field(default_factory=dict)
    constraint_values: dict[str, Any] = Field(default_factory=dict)


class PartialResponseValidationError(ValueError):
    """All independently checkable failures from the same grouped response."""

    def __init__(self, issues: tuple[PartialResponseIssue, ...]):
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


def inspect_partial_response(
    value: Any, schema: Mapping[str, Any], plan: PartialRequestPlan
) -> tuple[PartialResponseIssue, ...]:
    """Collect schema AND cross-attribute errors without accepting or editing values.

    A malformed field does not prevent inspection of unrelated, well-shaped pairs.
    Omission is not a negative; a null primary does not introduce a new nonempty-set
    rule. Acceptance is unchanged from the original strict grouped contract.
    """
    candidate = dict(value) if isinstance(value, Mapping) else value
    errors = sorted(Draft202012Validator(schema).iter_errors(candidate), key=lambda e: e.message)
    issues = []
    for error in errors:
        path = tuple(error.absolute_path)
        fields = (str(path[0]),) if path else ()
        issues.append(
            PartialResponseIssue(
                code=f"schema.{error.validator}",
                attributes=fields,
                path=path,
                message=f"partial response violates request schema: {error.message}",
                observed_values={key: candidate[key] for key in fields if key in candidate}
                if isinstance(candidate, dict)
                else {},
            )
        )
    if not isinstance(candidate, dict):
        return tuple(issues)
    constraints = {**plan.accepted_attributes, **plan.fixed_primary_constraints}
    combined = {**constraints, **candidate}
    for primary, collection in PRIMARY_SET_FIELDS:
        primary_value = combined.get(primary)
        collection_value = combined.get(collection)
        # Invalid shapes are already reported by the schema. Do not let them mask
        # another dimension or produce TypeError while comparing set membership.
        if isinstance(primary_value, str) and isinstance(collection_value, list):
            if primary_value not in collection_value:
                fields = (primary, collection)
                issues.append(
                    PartialResponseIssue(
                        code="primary_not_in_set",
                        attributes=fields,
                        message=f"{primary} must belong to the explicitly evaluated {collection}",
                        observed_values={key: candidate[key] for key in fields if key in candidate},
                        constraint_values={
                            key: constraints[key] for key in fields if key in constraints
                        },
                    )
                )
    if (
        combined.get("role_semantics_present") is False
        and isinstance(combined.get("role_relations"), list)
        and combined["role_relations"]
    ):
        fields = ("role_semantics_present", "role_relations")
        issues.append(
            PartialResponseIssue(
                code="negative_presence_with_relations",
                attributes=fields,
                message="nonempty role_relations conflict with evaluated negative role presence",
                observed_values={key: candidate[key] for key in fields if key in candidate},
                constraint_values={key: constraints[key] for key in fields if key in constraints},
            )
        )
    return tuple(issues)


def partial_response_diagnostics(
    value: Any, schema: Mapping[str, Any], plan: PartialRequestPlan
) -> dict[str, Any]:
    """Portable review evidence, not partial acceptance or additional model votes."""
    issues = inspect_partial_response(value, schema, plan)
    return {
        "contract": "strict-grouped-v1",
        "diagnostic_version": "all-errors-v1",
        "valid": not issues,
        "acceptance_changed": False,
        "issues": [item.model_dump(mode="json") for item in issues],
        "response_values": dict(value) if isinstance(value, Mapping) else value,
        "provided_fields": sorted(value) if isinstance(value, Mapping) else [],
        "requested_attributes": list(plan.requested_attributes),
        "fixed_primary_constraints": plan.fixed_primary_constraints,
        "accepted_attribute_constraints": plan.accepted_attributes,
    }


def validate_partial_response(
    value: Mapping[str, Any], schema: Mapping[str, Any], plan: PartialRequestPlan
) -> dict[str, Any]:
    """Validate strictly; report all conflicts without coercion or invented members.

    A malformed grouped answer still fails the group. Diagnostic values are not
    salvaged into consensus; that would be a separate acceptance contract.
    """
    issues = inspect_partial_response(value, schema, plan)
    if issues:
        raise PartialResponseValidationError(issues)
    return dict(value)
