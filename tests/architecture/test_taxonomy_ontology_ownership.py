"""Guard taxonomy, accepted enrichment, and qualification ownership boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

APPLICATION = Path("src/standards_atlas/application")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_legacy_mixed_semantic_classifier_is_removed() -> None:
    assert not (APPLICATION / "services" / "semantic_classifier.py").exists()


def test_content_enrichment_does_not_classify_taxonomy_or_ontology() -> None:
    path = APPLICATION / "services" / "content_enrichment_service.py"
    imports = _imports(path)

    assert not any(
        module.startswith("standards_atlas.application.semantic_ontology") for module in imports
    )
    assert "standards_atlas.application.services.structural_profile_classifier" not in imports


def test_legacy_semantic_classification_service_is_removed() -> None:
    assert not (APPLICATION / "services" / "semantic_enrichment_service.py").exists()
    assert not (APPLICATION / "semantic_classification").exists()


def test_qualification_does_not_materialize_semantic_enrichment() -> None:
    """Candidate qualification code must not write accepted document enrichment."""

    qualification_files = tuple((APPLICATION / "semantic_qualification").rglob("*.py"))
    assert qualification_files, "semantic qualification package not found"
    for path in qualification_files:
        imports = _imports(path)
        assert not any(
            module.startswith("standards_atlas.application.services.semantic_enrichment_service")
            for module in imports
        ), path
