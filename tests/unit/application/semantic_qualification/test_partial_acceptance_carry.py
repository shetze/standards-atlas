"""Versioned carry excludes accepted questions without synthesizing answers."""

import pytest
from test_mixed_consensus import VALUES
from test_partial_observations import RESOURCES, config, example

from standards_atlas.application.semantic_qualification.partial_observations import (
    validate_partial_response,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    run_partial_proposals,
)
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialTaskResources,
    prepare_partial_request,
)


def prepare(
    *, accepted=None, state="a" * 64, selected=None, prompt="taxonomy-partial-v2", item=None
):
    cfg = config(
        prompt_version=prompt, **({"selected_attributes": selected} if selected is not None else {})
    )
    item = item or example()
    return prepare_partial_request(
        cfg,
        item.id,
        item.input,
        PartialTaskResources.load(RESOURCES, cfg),
        accepted_attributes=accepted,
        accepted_state_sha256=state,
    )


def test_old_v1_payload_retains_old_wire_fields_and_version():
    old = prepare(prompt="taxonomy-partial-v1", state=None)
    payload = old.plan.model_dump(mode="json")
    assert payload["schema_version"] == "1.0"
    assert "accepted_attributes" not in payload and "accepted_state_sha256" not in payload


def test_v2_declares_schema_even_without_any_prior_acceptance():
    assert prepare(state=None).plan.schema_version == "1.1"


def test_carry_primary_removes_only_primary_and_constrains_its_open_set():
    request = prepare(accepted={"primary_function": "definition"})
    assert "primary_function" not in request.plan.requested_attributes
    assert "statement_functions" in request.plan.requested_attributes
    assert request.plan.fixed_primary_constraints["primary_function"] == "definition"
    assert '"primary_function": "definition"' in request.request.user_prompt


def test_carry_requires_real_state_identity_and_v2_prompt():
    with pytest.raises(ValueError):
        prepare(accepted={"primary_function": "definition"}, state=None)
    with pytest.raises(ValueError, match="v2"):
        prepare(accepted={"primary_function": "definition"}, prompt="taxonomy-partial-v1")


def test_carry_changes_request_identity_even_if_open_question_set_is_same():
    first = prepare(accepted={"primary_function": "definition"})
    second = prepare(accepted={"primary_function": "description"})
    assert first.fingerprint != second.fingerprint
    assert first.plan.requested_attributes == second.plan.requested_attributes
    assert (
        first.fingerprint
        != prepare(accepted={"primary_function": "definition"}, state="b" * 64).fingerprint
    )


def test_accepted_negative_role_presence_cannot_return_nonempty_relations():
    request = prepare(accepted={"role_semantics_present": False})
    values = {k: VALUES[k] for k in request.plan.requested_attributes}
    values["role_relations"] = [
        {"actor": "supplier", "relation_class": "responsibility", "target": "review"}
    ]
    with pytest.raises(ValueError, match="negative role presence"):
        validate_partial_response(values, request.request.output_schema, request.plan)


def test_already_accepted_set_constrains_still_open_primary():
    request = prepare(accepted={"knowledge_kinds": ["process"]})
    values = {k: VALUES[k] for k in request.plan.requested_attributes}
    values["primary_knowledge_kind"] = "concept"
    with pytest.raises(ValueError, match="explicitly evaluated"):
        validate_partial_response(values, request.request.output_schema, request.plan)


def test_fully_accepted_current_plan_skips_gateway_with_empty_model_evidence(tmp_path):
    item = example()

    def never():
        pytest.fail("no questions remain")

    result = run_partial_proposals(
        config(prompt_version="taxonomy-partial-v2"),
        examples=(item,),
        resources=RESOURCES,
        output_directory=tmp_path / "run",
        execute=True,
        gateway_factory=never,
        accepted_decisions={item.id: VALUES},
        accepted_state_sha256="a" * 64,
    )
    assert result["logical_model_observation_count"] == 0
    assert result["request_timing"]["request_count"] == 0
    assert result["status_counts"] == {"not_requested": 1}
