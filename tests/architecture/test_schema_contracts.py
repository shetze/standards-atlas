"""R5 executable inventory: no schema drift hidden by models, envelopes or resources."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Literal, get_args, get_origin

import pytest
import yaml
from pydantic_core import PydanticUndefined

from standards_atlas.application.schema import (
    SCHEMA_ENVELOPE_DECISIONS,
    SCHEMA_ENVELOPE_MARKER_COUNTS,
    SCHEMA_MARKER_DECISIONS,
    SCHEMA_POLICIES,
    VERSIONED_INTERFACES,
    CompatibilityPhase,
    SchemaMarkerDisposition,
    require_current_payload,
    require_current_schema,
    validate_schema_registry,
)
from standards_atlas.application.schema.bindings import (
    SCHEMA_MARKER_BINDINGS,
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
    bindings = (
        *SCHEMA_MARKER_BINDINGS,
        *SCHEMA_MODEL_BINDINGS,
        *SCHEMA_WRITER_BINDINGS,
        *SCHEMA_RESOURCE_BINDINGS,
    )
    envelope_families = {
        family
        for decision in SCHEMA_ENVELOPE_DECISIONS
        if decision.disposition is SchemaMarkerDisposition.CENTRAL
        for family in decision.schema_families
    }
    assert {b.family for b in bindings} | envelope_families == set(SCHEMA_POLICIES)
    for entries in (
        SCHEMA_MARKER_BINDINGS,
        SCHEMA_MODEL_BINDINGS,
        SCHEMA_WRITER_BINDINGS,
        SCHEMA_RESOURCE_BINDINGS,
    ):
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
    serialized_name = field.serialization_alias or field.alias or "schema_version"
    assert serialized_name in output_schema.get("properties", {})


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


def _class_schema_markers() -> dict[str, str | None]:
    markers: dict[str, str | None] = {}
    for path in (ROOT / "src/standards_atlas").rglob("*.py"):
        tree = ast.parse(path.read_text())
        module = ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            has_schema_version = any(
                isinstance(item, (ast.Assign, ast.AnnAssign))
                and any(
                    isinstance(target, ast.Name) and target.id == "schema_version"
                    for target in (item.targets if isinstance(item, ast.Assign) else (item.target,))
                )
                for item in node.body
            )
            if not has_schema_version:
                continue
            family = None
            for item in node.body:
                if (
                    isinstance(item, ast.AnnAssign)
                    and isinstance(item.target, ast.Name)
                    and item.target.id == "SCHEMA_FAMILY"
                    and isinstance(item.value, ast.Constant)
                ):
                    family = item.value.value
                    break
            markers[f"{module}:{node.name}"] = family
    return markers


def test_every_class_schema_marker_has_an_explicit_architecture_decision_or_binding():
    markers = _class_schema_markers()
    decisions = {item.reference: item for item in SCHEMA_MARKER_DECISIONS}
    model_bindings = {item.reference: item.family for item in SCHEMA_MODEL_BINDINGS}
    marker_bindings = {item.reference: item.family for item in SCHEMA_MARKER_BINDINGS}

    assert len(decisions) == len(SCHEMA_MARKER_DECISIONS)
    assert set(decisions) <= set(markers)

    for reference, family in markers.items():
        decision = decisions.get(reference)
        if family is not None:
            assert model_bindings.get(reference) == family, reference
            if decision is not None:
                assert decision.disposition.value == "central"
                assert decision.schema_family == family
            continue

        assert decision is not None, reference
        if decision.disposition.value == "central":
            assert marker_bindings.get(reference) == decision.schema_family, reference
            assert decision.schema_family in SCHEMA_POLICIES
        else:
            assert decision.reason
            assert reference not in marker_bindings


def _schema_version_subscript(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and node.slice.value == "schema_version"
    )


class _SchemaEnvelopeVisitor(ast.NodeVisitor):
    """Collect raw mapping schema markers by their nearest function scope."""

    def __init__(self, module: str) -> None:
        self.module = module
        self.scope: list[str] = []
        self.counts: dict[str, int] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _record_marker(self) -> None:
        reference = f"{self.module}:{'.'.join(self.scope)}"
        self.counts[reference] = self.counts.get(reference, 0) + 1

    def visit_Dict(self, node: ast.Dict) -> None:
        if any(
            isinstance(key, ast.Constant) and key.value == "schema_version"
            for key in node.keys
            if key is not None
        ):
            self._record_marker()
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "dict"
            and any(keyword.arg == "schema_version" for keyword in node.keywords)
        ):
            self._record_marker()
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if any(_schema_version_subscript(target) for target in node.targets):
            self._record_marker()
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if _schema_version_subscript(node.target):
            self._record_marker()
        self.generic_visit(node)


def _schema_envelope_marker_counts_for_source(source: str, module: str) -> dict[str, int]:
    visitor = _SchemaEnvelopeVisitor(module)
    visitor.visit(ast.parse(source))
    return visitor.counts


def _schema_envelope_marker_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in (ROOT / "src/standards_atlas").rglob("*.py"):
        module = ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)
        discovered = _schema_envelope_marker_counts_for_source(path.read_text(), module)
        for reference, count in discovered.items():
            counts[reference] = counts.get(reference, 0) + count
    return counts


def _scope_node(reference: str) -> ast.AST:
    module, symbol = reference.split(":")
    path = ROOT / "src" / Path(*module.split(".")).with_suffix(".py")
    scope: list[ast.stmt] = ast.parse(path.read_text()).body
    node: ast.AST | None = None
    for part in symbol.split("."):
        node = next(
            item
            for item in scope
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and item.name == part
        )
        scope = node.body
    assert node is not None
    return node


def _current_payload_guard_families(node: ast.AST) -> set[str]:
    return {
        call.args[0].value
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "require_current_payload"
        and len(call.args) >= 2
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    }


def test_raw_schema_envelope_inventory_matches_all_source_markers_exactly():
    actual = _schema_envelope_marker_counts()
    expected = dict(SCHEMA_ENVELOPE_MARKER_COUNTS)
    assert len(expected) == len(SCHEMA_ENVELOPE_MARKER_COUNTS)
    assert actual == expected


def test_every_raw_schema_envelope_scope_is_bound_or_explicitly_classified():
    actual = _schema_envelope_marker_counts()
    writer_scopes = {binding.reference for binding in SCHEMA_WRITER_BINDINGS}
    decisions = {decision.reference: decision for decision in SCHEMA_ENVELOPE_DECISIONS}

    assert len(decisions) == len(SCHEMA_ENVELOPE_DECISIONS)
    assert set(decisions) <= set(actual)
    assert set(actual) == writer_scopes | set(decisions)

    for reference, decision in decisions.items():
        assert decision.marker_count == actual[reference]
        if decision.disposition is SchemaMarkerDisposition.LOCAL:
            assert decision.reason
            continue
        assert set(decision.schema_families) <= set(SCHEMA_POLICIES)
        guards = _current_payload_guard_families(_scope_node(reference))
        assert set(decision.schema_families) <= guards, (
            reference,
            set(decision.schema_families) - guards,
        )


def test_unclassified_raw_schema_envelope_is_detectable_by_discovery_guard():
    discovered = _schema_envelope_marker_counts_for_source(
        (
            "def publish():\n"
            '    payload = {"schema_version": 1}\n'
            "    alternate = dict(schema_version=1)\n"
            '    payload["schema_version"] = 1\n'
            "    return payload, alternate\n"
        ),
        "synthetic.module",
    )
    assert discovered == {"synthetic.module:publish": 3}
    writer_scopes = {binding.reference for binding in SCHEMA_WRITER_BINDINGS}
    decisions = {decision.reference for decision in SCHEMA_ENVELOPE_DECISIONS}
    unclassified = set(discovered) - writer_scopes - decisions
    assert unclassified == {"synthetic.module:publish"}
