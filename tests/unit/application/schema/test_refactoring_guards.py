"""Current-only policy and actual serializer guards, not a compatibility migration."""

from __future__ import annotations

import copy
import importlib
import warnings
from typing import ClassVar, Literal

import pytest

from standards_atlas.application.schema import (
    SCHEMA_POLICIES,
    CompatibilityPhase,
    SchemaDeprecationWarning,
    SchemaPolicy,
    require_current_payload,
    require_current_schema,
    require_supported_schema,
    validate_schema_registry,
)
from standards_atlas.application.schema.bindings import SCHEMA_MODEL_BINDINGS
from standards_atlas.application.schema.model import SchemaBoundModel


@pytest.mark.parametrize("family", sorted(SCHEMA_POLICIES))
def test_every_concrete_family_is_type_exact_current_only(family):
    current = SCHEMA_POLICIES[family].current
    require_supported_schema(family, current)
    require_current_schema(family, current)
    wrong = [None, False, True, [], {}, "", "obsolete", 1.0]
    wrong.append(str(current) if type(current) is int else 1)
    for value in wrong:
        with pytest.raises(ValueError, match="schema version"):
            require_supported_schema(family, value)
        with pytest.raises(ValueError, match="writers may only emit"):
            require_current_schema(family, value)


@pytest.mark.parametrize(
    "current,readable",
    [
        ("1.1", ("1.0", "1.1")),
        (3, (1, 2, 3)),
    ],
)
def test_refactoring_cannot_register_a_legacy_window(current, readable):
    with pytest.raises(ValueError, match="Refactoring requires current-only"):
        SchemaPolicy("test", current, readable, "test")


@pytest.mark.parametrize(
    "current,readable",
    [
        (True, (True,)),
        (1.0, (1.0,)),
        ("", ("",)),
        ("1", (1, "1")),
        (1, (1, 1)),
        (1, [1]),
        (1, ()),
    ],
)
def test_malformed_policy_definitions_fail(current, readable):
    with pytest.raises(ValueError):
        SchemaPolicy("test", current, readable, "test")


def test_synthetic_stable_infrastructure_does_not_reopen_production_windows(monkeypatch):
    stable = SchemaPolicy("example", 3, (1, 2, 3), "test", phase=CompatibilityPhase.STABLE)
    validate_schema_registry({"example": stable}, phase=CompatibilityPhase.STABLE)
    with pytest.warns(SchemaDeprecationWarning, match="oldest supported"):
        stable.require_readable(1)
    with pytest.warns(SchemaDeprecationWarning, match="deprecated"):
        stable.require_readable(2)
    with pytest.raises(ValueError):
        stable.require_current_for_write(2)
    with pytest.raises(ValueError, match="phase differs"):
        validate_schema_registry({"example": stable})
    monkeypatch.setitem(SCHEMA_POLICIES, "example", stable)
    for guard in (require_supported_schema, require_current_schema):
        with pytest.raises(ValueError, match="phase differs"):
            guard("example", 3)


def test_registry_rejects_wrong_key_empty_and_unknown_families():
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_schema_registry({})
    with pytest.raises(ValueError, match="key differs"):
        validate_schema_registry({"wrong": SchemaPolicy("other", 1, (1,), "test")})
    with pytest.raises(ValueError, match="unregistered"):
        require_current_schema("not-a-contract", "1.0")


@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {"schema_version": None}, {"schema_version": 1.0}],
)
def test_writer_payload_cannot_acquire_an_implicit_or_coerced_version(payload):
    with pytest.raises(ValueError):
        require_current_payload("semantic-extraction", payload)


def test_payload_guard_neither_mutates_nor_infers_nested_contracts():
    payload = {"schema_version": 1, "attachment": {"schema_version": "opaque"}, "value": False}
    before = copy.deepcopy(payload)
    assert require_current_payload("semantic-extraction", payload) is None
    assert payload == before


@pytest.mark.parametrize("binding", SCHEMA_MODEL_BINDINGS, ids=lambda b: b.family)
@pytest.mark.parametrize("mode", ["python", "json"])
def test_every_bound_serializer_rejects_unchecked_marker_before_handling_fields(binding, mode):
    module, symbol = binding.reference.split(":")
    cls = getattr(importlib.import_module(module), symbol)
    # Missing required content is deliberate: the schema guard must run first.
    broken = cls.model_construct(schema_version="obsolete")
    before = copy.deepcopy(broken.__dict__)
    with pytest.raises(ValueError, match="writers may only emit"):
        broken.model_dump(mode=mode)
    assert broken.__dict__ == before


class Sample(SchemaBoundModel):
    SCHEMA_FAMILY: ClassVar[str] = "review-profile"
    schema_version: Literal[1] = 1
    value: bool = False


def test_guard_preserves_current_bytes_and_rejects_copy_even_with_version_excluded():
    item = Sample()
    assert item.model_dump_json() == '{"schema_version":1,"value":false}'
    assert item.model_dump(exclude={"schema_version"}) == {"value": False}
    for mode in ("json", "python"):
        for shadow in (None, "engineering-document", "review-profile"):
            bad = item.model_copy(update={"schema_version": "obsolete", "SCHEMA_FAMILY": shadow})
            with pytest.raises(ValueError, match="writers may only emit"):
                bad.model_dump(mode=mode, exclude={"schema_version"})


def test_writer_uses_actual_model_marker_after_policy_changes(monkeypatch):
    item = Sample()
    monkeypatch.setitem(
        SCHEMA_POLICIES,
        "review-profile",
        SchemaPolicy("review-profile", 2, (2,), "test"),
    )
    with pytest.raises(ValueError, match="writers may only emit"):
        item.model_dump_json()
    assert item.schema_version == 1


def test_unexpected_schema_deprecation_is_a_test_error():
    with pytest.raises(SchemaDeprecationWarning):
        warnings.warn("unexpected production deprecation", SchemaDeprecationWarning, stacklevel=2)


@pytest.mark.parametrize("binding", SCHEMA_MODEL_BINDINGS, ids=lambda b: b.family)
def test_json_reads_cannot_acquire_a_defaulted_schema_marker(binding):
    module, symbol = binding.reference.split(":")
    cls = getattr(importlib.import_module(module), symbol)
    with pytest.raises(ValueError, match="schema_version"):
        cls.model_validate_json("{}")


def test_nested_json_contract_requires_marker_without_versioning_plain_builder_models():
    from pydantic import BaseModel

    class Wrapper(BaseModel):
        child: Sample

    # New Python objects retain their explicit construction defaults.
    built = Wrapper(child=Sample())
    assert built.model_dump_json() == '{"child":{"schema_version":1,"value":false}}'
    with pytest.raises(ValueError, match="schema_version"):
        Wrapper.model_validate_json('{"child":{"value":false}}')
    assert Wrapper.model_validate_json(built.model_dump_json()) == built
