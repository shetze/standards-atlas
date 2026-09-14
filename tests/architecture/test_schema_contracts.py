"""R4 executable inventory: no schema drift hidden by defaults, copies or resources."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Literal, get_args, get_origin

import pytest
import yaml
from pydantic_core import PydanticUndefined

from standards_atlas.application.schema import (
    SCHEMA_POLICIES,
    VERSIONED_INTERFACES,
    CompatibilityPhase,
    require_current_payload,
    require_current_schema,
    validate_schema_registry,
)
from standards_atlas.application.schema.bindings import (
    SCHEMA_MODEL_BINDINGS,
    SCHEMA_RESOURCE_BINDINGS,
    SCHEMA_WRITER_BINDINGS,
)
from standards_atlas.application.schema.model import SchemaBoundModel

ROOT = Path(__file__).resolve().parents[2]


def resolve(reference):
    module, symbol = reference.split(":")
    value = importlib.import_module(module)
    for part in symbol.split("."):
        value = getattr(value, part)
    return value


def test_refactoring_registry_inventory_and_boundary_coverage_are_complete():
    validate_schema_registry()
    assert all(p.phase is CompatibilityPhase.REFACTORING for p in SCHEMA_POLICIES.values())
    assert all(p.readable == (p.current,) for p in SCHEMA_POLICIES.values())
    interfaces = [i.schema_family for i in VERSIONED_INTERFACES if i.schema_family]
    assert len(interfaces) == len(set(interfaces))
    assert len({i.id for i in VERSIONED_INTERFACES}) == len(VERSIONED_INTERFACES)
    assert set(interfaces) == set(SCHEMA_POLICIES)
    bindings = (*SCHEMA_MODEL_BINDINGS, *SCHEMA_WRITER_BINDINGS, *SCHEMA_RESOURCE_BINDINGS)
    assert {b.family for b in bindings} == set(SCHEMA_POLICIES)
    for entries in (SCHEMA_MODEL_BINDINGS, SCHEMA_WRITER_BINDINGS, SCHEMA_RESOURCE_BINDINGS):
        assert len(set(entries)) == len(entries)


@pytest.mark.parametrize("binding", SCHEMA_MODEL_BINDINGS, ids=lambda b: b.family)
def test_model_literal_default_and_serialization_guard_match_registry(binding):
    cls = resolve(binding.reference)
    assert issubclass(cls, SchemaBoundModel)
    assert cls.SCHEMA_FAMILY == binding.family
    field = cls.model_fields["schema_version"]
    assert field.default_factory is None  # Never derive a marker from a changing registry.
    current = SCHEMA_POLICIES[binding.family].current
    if get_origin(field.annotation) is Literal:
        assert get_args(field.annotation) == (current,)
        assert type(get_args(field.annotation)[0]) is type(current)
    else:
        assert field.annotation is type(current)
    if field.default is not PydanticUndefined:
        require_current_schema(binding.family, field.default)
    # No subclass serializer may silently shadow the central guard.
    assert cls.__pydantic_serializer__ is not None
    assert cls.current_schema_serialization is SchemaBoundModel.current_schema_serialization
    serializers = cls.__pydantic_decorators__.model_serializers
    assert set(serializers) == {"current_schema_serialization"}
    # A typed Any/dict return on a wrap serializer would silently erase the
    # published output schema even while normal model_dump tests still pass.
    output_schema = cls.model_json_schema(mode="serialization")
    assert output_schema.get("type") == "object"
    assert "schema_version" in output_schema.get("properties", {})


@pytest.mark.parametrize("binding", SCHEMA_WRITER_BINDINGS, ids=lambda b: b.family)
def test_dict_writer_checks_its_actual_envelope(binding):
    module, symbol = binding.reference.split(":")
    path = ROOT / "src" / Path(*module.split(".")).with_suffix(".py")
    scope = ast.parse(path.read_text()).body
    for part in symbol.split("."):
        node = next(
            n for n in scope if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == part
        )
        scope = node.body
    calls = [
        n
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "require_current_payload"
        and len(n.args) == 2
        and isinstance(n.args[0], ast.Constant)
        and n.args[0].value == binding.family
    ]
    assert calls, f"{binding.reference} must guard its actual {binding.family} payload"
    assert all(isinstance(n.args[1], (ast.Name, ast.Subscript)) for n in calls)


@pytest.mark.parametrize("binding", SCHEMA_RESOURCE_BINDINGS, ids=lambda b: b.family)
def test_all_shipped_resource_variants_use_current_serialization(binding):
    matched = []
    for path in sorted(ROOT.glob(binding.pattern)):
        raw = yaml.safe_load(path.read_bytes())
        if binding.discriminator:
            key, expected = binding.discriminator
            if not isinstance(raw, dict) or raw.get(key) != expected:
                continue
        require_current_payload(binding.family, raw)
        matched.append(path)
    assert matched, f"empty resource guard: {binding}"


def test_all_declared_model_bindings_and_literal_guard_families_are_in_inventory():
    expected = {(b.family, b.reference) for b in SCHEMA_MODEL_BINDINGS}
    actual = set()
    for path in (ROOT / "src/standards_atlas").rglob("*.py"):
        tree = ast.parse(path.read_text())
        module = ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if (
                        isinstance(item, ast.AnnAssign)
                        and isinstance(item.target, ast.Name)
                        and item.target.id == "SCHEMA_FAMILY"
                        and isinstance(item.value, ast.Constant)
                        and item.value.value is not None
                    ):
                        actual.add((item.value.value, f"{module}:{node.name}"))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id
                in {
                    "require_current_schema",
                    "require_supported_schema",
                    "require_current_payload",
                }
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                assert node.args[0].value in SCHEMA_POLICIES, (path, node.lineno)
    assert actual == expected


def test_obsolete_aliases_are_not_exported():
    import standards_atlas.application.schema as schema
    import standards_atlas.application.schema.baseline as baseline

    for module in (schema, baseline):
        assert not hasattr(module, "SCHEMA_BASELINES")
        assert not hasattr(module, "SchemaBaseline")
