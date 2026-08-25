"""Guard the formal semantic model against adapter/framework coupling."""

from __future__ import annotations

import ast
from pathlib import Path

MODEL = Path("src/standards_atlas/domain/model/formal_semantics.py")
PORT = Path("src/standards_atlas/application/ports/formal_semantics.py")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_formal_semantic_model_is_graph_provider_neutral() -> None:
    imports = _imports(MODEL) | _imports(PORT)
    forbidden = ("rdflib", "owlready", "neo4j", "graphrag")
    assert not any(module.startswith(forbidden) for module in imports)


def test_stable_namespace_is_declared_once_in_domain_contract() -> None:
    source = MODEL.read_text(encoding="utf-8")
    assert 'FORMAL_SEMANTIC_NAMESPACE = "http://lunetix.org/standards-atlas#"' in source
    assert 'FORMAL_SEMANTIC_PREFIX = "stat"' in source
