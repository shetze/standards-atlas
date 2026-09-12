"""Partial task invariants: no defaults, no invented set members, no fake votes."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from standards_atlas.application.context.source_structure import project_source_structure
from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_ATTRIBUTES,
    PartialObservation,
    PartialRequestPlan,
    observation_states,
    validate_partial_response,
)
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialProposalConfig,
    PartialTaskResources,
    prepare_partial_request,
)
from standards_atlas.application.semantic_qualification.request_builder import (
    build_proposal_request,
)
from standards_atlas.domain.model import Clause, ClauseId, ClauseType, StandardReference, TextBlock

RESOURCES = Path("src/standards_atlas/resources/semantic")


def config(**changes):
    return PartialProposalConfig(
        corpus_id="test-partial",
        dataset_version="1",
        provider="fake",
        model="small",
        retry_backoff_seconds=0,
        **changes,
    )


def example(identity="a", *, confirmed=False, **context):
    text = "A sequence of activities. NOTE: The requirements of 7 do not apply."
    clause = Clause(
        id=ClauseId(value=identity),
        reference=StandardReference(standard="TEST", clause="3.1"),
        clause_type=ClauseType.TERM,
        heading="process",
        content=(TextBlock(id="text", text=text),),
    )
    if confirmed:
        clause = clause.confirm_authoritative("clause_type", authority="reviewed-source")
    content_hash = normalized_content_hash(text)
    payload = {
        "knowledge_domain": "test",
        "document_key": "TEST",
        "clause_id": identity,
        "reference": "3.1",
        "clause_type": "term",
        "heading": "process",
        **context,
    }
    if confirmed:
        source = project_source_structure(clause, document_key="TEST", content_hash=content_hash)
        payload["source_structure"] = source.model_dump(mode="json")
    return EvaluationExample(
        id=identity,
        input={"content": {"text": text, "hash": content_hash}, "context": payload},
        expected={"applicability_present": True},
        tags=("golden-positive",),
    )


def prepared(*, cfg=None, item=None):
    cfg, item = cfg or config(), item or example()
    resources = PartialTaskResources.load(RESOURCES, cfg)
    return prepare_partial_request(cfg, item.id, item.input, resources)


def observation(item, values, outcome="evaluated", **overrides):
    return PartialObservation(
        plan=item.plan,
        request_fingerprint=item.fingerprint,
        provider="fake",
        model="small",
        outcome=outcome,
        states=observation_states(item.plan, outcome),
        values=values,
        provided_fields=tuple(sorted(values)),
        response_sha256="1" * 64,
        **overrides,
    )


def test_confirmed_primary_keeps_secondary_set_and_every_other_question_open():
    item = prepared(item=example(confirmed=True))
    assert item.plan.fixed_attributes == {"primary_function": "definition"}
    assert "primary_function" not in item.plan.requested_attributes
    assert "statement_functions" in item.plan.requested_attributes
    assert len(item.plan.requested_attributes) == 8
    assert item.plan.fixed_primary_constraints == {"primary_function": "definition"}
    assert item.plan.decision_plan.diagnostic_only is True
    assert '"primary_function": "definition"' in item.request.user_prompt
    assert "primary_function" not in item.request.output_schema["properties"]


def test_unconfirmed_terms_and_hint_or_conflict_values_remain_requested():
    for item in (example(), example(clause_type="objective", heading="Work products")):
        result = prepared(item=item)
        assert result.plan.requested_attributes == PARTIAL_ATTRIBUTES
        assert result.plan.fixed_attributes == {}
        assert result.plan.request_count == 1


def test_fixed_primary_conditions_apply_to_an_open_set_even_when_primary_is_not_selected():
    result = prepared(
        cfg=config(selected_attributes=("statement_functions",)), item=example(confirmed=True)
    )
    assert result.plan.fixed_attributes == {}
    assert result.plan.fixed_primary_constraints == {"primary_function": "definition"}
    assert result.plan.requested_attributes == ("statement_functions",)


@pytest.mark.parametrize("attributes", [(), ("primary_function",)])
def test_zero_questions_do_not_create_a_request(attributes):
    item = prepared(cfg=config(selected_attributes=attributes), item=example(confirmed=True))
    assert item.request is None
    assert item.plan.request_count == 0
    assert item.plan.requested_attributes == ()


@pytest.mark.parametrize(
    "fields",
    [
        ("applicability_functions",),
        ("role_relation_types",),
        ("usability",),
        ("primary_function", "primary_function"),
    ],
)
def test_old_or_duplicate_fields_are_rejected(fields):
    with pytest.raises(ValueError):
        config(selected_attributes=fields)


@pytest.mark.parametrize(
    "option",
    [
        {"task_version": "2.5.0"},
        {"task": "semantic-profile-classification"},
        {"prompt_version": "structure-aware-v10"},
        {"cbox_frame": "full-context-v1"},
        {"adaptive_interview": True},
        {"overwrite": True},
        {"adaptive_question_max_tokens": 100},
    ],
)
def test_experimental_task_cannot_masquerade_as_old_contract(option):
    with pytest.raises(ValueError):
        config(**option)


def test_selected_field_order_is_canonical_and_has_no_impact_on_identity():
    first = prepared(cfg=config(selected_attributes=("applicability_present", "primary_function")))
    second = prepared(cfg=config(selected_attributes=("primary_function", "applicability_present")))
    assert first.fingerprint == second.fingerprint


@pytest.mark.parametrize("attribute", PARTIAL_ATTRIBUTES)
def test_each_attribute_has_an_individually_required_closed_schema(attribute):
    item = prepared(cfg=config(selected_attributes=(attribute,)))
    schema = item.request.output_schema
    Draft202012Validator.check_schema(schema)
    assert schema["required"] == [attribute]
    assert set(schema["properties"]) == {attribute, "confidence", "rationale"}
    assert schema["additionalProperties"] is False
    assert attribute in item.request.user_prompt


@pytest.mark.parametrize("value", [False, True])
def test_explicit_presence_is_one_observation_and_absent_fields_have_no_vote(value):
    item = prepared(cfg=config(selected_attributes=("applicability_present",)))
    values = validate_partial_response(
        {"applicability_present": value}, item.request.output_schema, item.plan
    )
    result = observation(item, values)
    assert result.model_evidence() == {"applicability_present": value}
    assert result.provided_fields == ("applicability_present",)
    assert result.values.get("role_semantics_present") is None
    assert "role_semantics_present" not in result.model_evidence()
    assert sum(state.status == "evaluated" for state in result.states) == 1
    encoded = json.loads(result.model_dump_json())
    assert encoded["values"] == {"applicability_present": value}
    assert PartialObservation.model_validate(encoded).model_evidence() == result.model_evidence()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"applicability_present": None},
        {"applicability_present": "false"},
        {"applicability_present": 0},
        {"applicability_present": False, "knowledge_kinds": []},
        {"applicability_present": False, "applicability_functions": []},
        {"applicability_present": False, "confidence": 2},
    ],
)
def test_missing_wrong_or_unrequested_fields_fail_without_normalization(payload):
    item = prepared(cfg=config(selected_attributes=("applicability_present",)))
    with pytest.raises(ValueError):
        validate_partial_response(payload, item.request.output_schema, item.plan)


def test_requested_null_primary_is_observed_but_does_not_infer_an_empty_set():
    item = prepared(cfg=config(selected_attributes=("primary_function",)))
    values = validate_partial_response(
        {"primary_function": None}, item.request.output_schema, item.plan
    )
    assert observation(item, values).model_evidence() == {"primary_function": None}


@pytest.mark.parametrize(
    "payload",
    [
        {"statement_functions": []},
        {"statement_functions": ["description"]},
        {"statement_functions": ["definition", "definition"]},
    ],
)
def test_fixed_primary_is_not_silently_inserted_into_incomplete_or_duplicate_set(payload):
    item = prepared(
        cfg=config(selected_attributes=("statement_functions",)), item=example(confirmed=True)
    )
    with pytest.raises(ValueError):
        validate_partial_response(payload, item.request.output_schema, item.plan)


def test_secondary_members_are_preserved_without_observing_the_known_primary():
    item = prepared(
        cfg=config(selected_attributes=("primary_function", "statement_functions")),
        item=example(confirmed=True),
    )
    values = validate_partial_response(
        {"statement_functions": ["definition", "note"]}, item.request.output_schema, item.plan
    )
    result = observation(item, values)
    assert result.model_evidence() == {"statement_functions": ["definition", "note"]}
    primary = next(state for state in result.states if state.attribute == "primary_function")
    assert (primary.status, primary.reason) == ("not_requested", "fixed")


@pytest.mark.parametrize(
    "primary,collection,member",
    [
        ("primary_function", "statement_functions", "definition"),
        ("primary_knowledge_kind", "knowledge_kinds", "process"),
        ("primary_process_function", "process_functions", "activity"),
    ],
)
def test_joint_primary_and_set_must_agree(primary, collection, member):
    item = prepared(cfg=config(selected_attributes=(primary, collection)))
    with pytest.raises(ValueError, match="must belong"):
        validate_partial_response(
            {primary: member, collection: []}, item.request.output_schema, item.plan
        )


def test_current_role_tuple_contract_and_passive_role_presence():
    item = prepared(cfg=config(selected_attributes=("role_semantics_present", "role_relations")))
    relation = {"actor": "assessor", "relation_class": "independence", "target": "developer"}
    for payload in (
        {"role_semantics_present": True, "role_relations": []},
        {"role_semantics_present": True, "role_relations": [relation]},
        {"role_semantics_present": False, "role_relations": []},
    ):
        assert validate_partial_response(payload, item.request.output_schema, item.plan) == payload
    for payload in (
        {"role_semantics_present": False, "role_relations": [relation]},
        {"role_semantics_present": True, "role_relations": ["responsibility"]},
        {"role_semantics_present": True, "role_relations": [{"actor": "assessor"}]},
    ):
        with pytest.raises(ValueError):
            validate_partial_response(payload, item.request.output_schema, item.plan)


def test_role_tuples_alone_do_not_materialize_presence():
    item = prepared(cfg=config(selected_attributes=("role_relations",)))
    payload = {"role_relations": [{"actor": "A", "relation_class": "performance", "target": "B"}]}
    assert (
        observation(
            item, validate_partial_response(payload, item.request.output_schema, item.plan)
        ).model_evidence()
        == payload
    )


def test_failed_group_provides_no_evidence_even_for_present_response_fields():
    item = prepared(cfg=config(selected_attributes=("applicability_present",)))
    result = PartialObservation(
        plan=item.plan,
        request_fingerprint=item.fingerprint,
        provider="fake",
        model="small",
        outcome="failed",
        states=observation_states(item.plan, "failed"),
        error="missing field",
        provided_fields=("rationale",),
    )
    assert result.model_evidence() == {}
    assert result.values == {}
    state = next(s for s in result.states if s.attribute == "applicability_present")
    assert state.status == "failed"


@pytest.mark.parametrize(
    "field",
    [
        "enrichments",
        "semantic_profile",
        "golden",
        "routing_context",
        "decision_plan",
        "primary_subject",
    ],
)
def test_semantic_targets_are_not_input_or_cache_identity(field):
    item = example()
    modified = copy.deepcopy(item.input)
    modified["context"][field] = {
        "primary_function": "TARGET_SENTINEL",
        "applicability_present": False,
    }
    first = prepared(item=item)
    second = prepared(item=replace(item, input=modified, expected={"sentinel": True}))
    assert first.fingerprint == second.fingerprint
    assert first.request.user_prompt == second.request.user_prompt
    assert "TARGET_SENTINEL" not in json.dumps(second.request.metadata)
    assert "clause_context" not in second.request.metadata


def test_source_and_generation_and_question_changes_invalidate_identity():
    baseline = prepared()
    candidates = [
        prepared(item=example(heading="Objectives")),
        prepared(item=example(confirmed=True)),
        prepared(cfg=config(selected_attributes=("applicability_present",))),
        prepared(cfg=config(seed=12)),
        prepared(cfg=config(max_tokens=1200)),
        prepared(cfg=config(temperature=0.1)),
        prepared(cfg=config(truncation_retry_max_tokens=2048)),
        prepared(
            cfg=PartialProposalConfig(
                corpus_id="test-partial", dataset_version="1", provider="fake", model="another"
            )
        ),
    ]
    assert all(candidate.fingerprint != baseline.fingerprint for candidate in candidates)


def test_prompt_rule_and_task_changes_invalidate_identity(monkeypatch):
    from standards_atlas.application.semantic_qualification import partial_requests as module

    cfg, item = config(), example()
    resources = PartialTaskResources.load(RESOURCES, cfg)
    first = prepare_partial_request(cfg, item.id, item.input, resources)
    altered_prompt = replace(resources.prompt, system_prompt=resources.prompt.system_prompt + "\nX")
    other = prepare_partial_request(
        cfg, item.id, item.input, replace(resources, prompt=altered_prompt)
    )
    assert first.fingerprint != other.fingerprint
    original = module.derive_clause_decision_plan
    monkeypatch.setattr(
        module,
        "derive_clause_decision_plan",
        lambda *a, **kw: original(*a, **kw).model_copy(
            update={"rules_version": "1.0.1", "rules_sha256": "7" * 64}
        ),
    )
    other = prepare_partial_request(cfg, item.id, item.input, resources)
    assert first.fingerprint != other.fingerprint


def test_plan_rejects_fabricated_fixed_values_and_mismatched_source():
    item = prepared(item=example(confirmed=True))
    raw = item.plan.model_dump(mode="json")
    raw["fixed_attributes"]["primary_function"] = "requirement"
    with pytest.raises(ValidationError):
        PartialRequestPlan.model_validate(raw)
    raw = item.plan.model_dump(mode="json")
    raw["clause"]["clause_id"] = "other"
    with pytest.raises(ValidationError):
        PartialRequestPlan.model_validate(raw)


def test_extra_prompt_fields_cannot_override_source_content():
    cfg, item = config(), example()
    resource = PartialTaskResources.load(RESOURCES, cfg)
    with pytest.raises(ValueError, match="cannot replace source fields"):
        build_proposal_request(
            cfg,
            resource.prompt,
            item.input,
            resource.task,
            extra_template_values={"content": "replacement"},
        )


def test_full_clause_and_normative_note_survive_request_projection():
    item = example(confirmed=True)
    request = prepared(item=item).request
    assert item.input["content"]["text"] in request.user_prompt
    assert "The requirements of 7 do not apply" in request.user_prompt
    assert "applicability_present" in request.output_schema["required"]


def test_all_512_attribute_selections_preserve_sparse_observation_contract():
    """Exhaustive finite-subset test, without optional property-test dependencies."""
    cfg, source = config(), example(confirmed=True)
    resources = PartialTaskResources.load(RESOURCES, cfg)
    for bits in range(1 << len(PARTIAL_ATTRIBUTES)):
        selected = tuple(key for index, key in enumerate(PARTIAL_ATTRIBUTES) if bits & (1 << index))
        current = config(selected_attributes=selected)
        item = prepare_partial_request(current, source.id, source.input, resources)
        assert set(item.plan.requested_attributes) == set(selected) - {"primary_function"}
        if not item.plan.requested_attributes:
            assert item.request is None
            continue
        values = {
            key: False
            if key.endswith("_present")
            else []
            if key
            in {"statement_functions", "knowledge_kinds", "process_functions", "role_relations"}
            else None
            for key in item.plan.requested_attributes
        }
        if "statement_functions" in values:
            values["statement_functions"] = ["definition", "note"]
        validated = validate_partial_response(values, item.request.output_schema, item.plan)
        result = observation(item, validated)
        assert set(result.model_evidence()) == set(item.plan.requested_attributes)
        assert "primary_function" not in result.model_evidence()
        assert all(
            s.status == "not_requested"
            for s in result.states
            if s.attribute not in item.plan.requested_attributes
        )
