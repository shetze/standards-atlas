"""Executable guards for the inward dependency direction of the hexagonal architecture."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src" / "standards_atlas"


class ImportRef(tuple):
    """Resolved import reference represented as ``(path, line, module)``."""

    __slots__ = ()

    def __new__(cls, path: Path, line: int, module: str) -> ImportRef:
        return tuple.__new__(cls, (path, line, module))

    @property
    def path(self) -> Path:
        return self[0]

    @property
    def line(self) -> int:
        return self[1]

    @property
    def module(self) -> str:
        return self[2]


def _module_name(path: Path) -> str:
    relative = path.relative_to(PROJECT_ROOT / "src").with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_from_import(path: Path, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module

    current = _module_name(path).split(".")
    if path.name != "__init__.py":
        current = current[:-1]
    climb = node.level - 1
    if climb > len(current):
        return node.module
    prefix = current[: len(current) - climb]
    if node.module:
        prefix.extend(node.module.split("."))
    return ".".join(prefix)


def _imports(paths: Iterable[Path]) -> tuple[ImportRef, ...]:
    imports: list[ImportRef] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = _resolve_from_import(path, node)
                if module:
                    imports.append(ImportRef(path, node.lineno, module))
            elif isinstance(node, ast.Import):
                imports.extend(ImportRef(path, node.lineno, alias.name) for alias in node.names)
    return tuple(imports)


def _python_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(root.rglob("*.py")))


def _matches(module: str, forbidden: str) -> bool:
    return module == forbidden or module.startswith(f"{forbidden}.")


def _assert_no_imports(paths: Iterable[Path], forbidden: tuple[str, ...]) -> None:
    violations = [
        f"{ref.path.relative_to(PROJECT_ROOT)}:{ref.line} imports {ref.module}"
        for ref in _imports(paths)
        if any(_matches(ref.module, prefix) for prefix in forbidden)
    ]
    assert violations == []


def test_domain_dependencies_point_inward() -> None:
    """The domain is independent of orchestration and infrastructure packages."""

    _assert_no_imports(
        _python_files(SOURCE_ROOT / "domain"),
        (
            "standards_atlas.application",
            "standards_atlas.adapters",
            "standards_atlas.cli",
        ),
    )


def test_application_does_not_import_adapters_or_cli() -> None:
    """Application use cases depend on ports, never concrete outbound/inbound adapters."""

    _assert_no_imports(
        _python_files(SOURCE_ROOT / "application"),
        (
            "standards_atlas.adapters",
            "standards_atlas.cli",
        ),
    )


def test_domain_and_application_do_not_import_infrastructure_frameworks() -> None:
    """Concrete graph, document, AI, and publication technologies stay in adapters."""

    _assert_no_imports(
        (*_python_files(SOURCE_ROOT / "domain"), *_python_files(SOURCE_ROOT / "application")),
        (
            "docling",
            "doorstop",
            "langchain",
            "llama_index",
            "neo4j",
            "rdflib",
            "torch",
            "transformers",
        ),
    )


def test_generic_evaluation_does_not_depend_on_semantic_qualification() -> None:
    """Generic evaluation infrastructure must remain reusable outside standards semantics."""

    _assert_no_imports(
        _python_files(SOURCE_ROOT / "application" / "evaluation"),
        ("standards_atlas.application.semantic_qualification",),
    )


def test_structural_taxonomy_does_not_depend_on_semantic_classification() -> None:
    """Structural classification must remain deterministic and semantic-task independent."""

    structural_paths = [*_python_files(SOURCE_ROOT / "application" / "structure")]
    structural_paths.extend(
        path
        for path in (SOURCE_ROOT / "application" / "services").glob("structural*.py")
        if path.is_file()
    )
    structural_paths.extend(_python_files(SOURCE_ROOT / "adapters" / "structure_taxonomies"))

    _assert_no_imports(
        structural_paths,
        (
            "standards_atlas.application.semantic_ontology",
            "standards_atlas.application.semantic_classification",
            "standards_atlas.application.semantic_extraction",
            "standards_atlas.resources.ontologies",
            "standards_atlas.resources.semantic",
        ),
    )
