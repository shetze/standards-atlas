"""Architecture guards for deterministic Slice-3 projection."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECTOR = Path("src/standards_atlas/application/formal_semantics/projector.py")
RDF_ADAPTER = Path("src/standards_atlas/adapters/rdf/turtle_projection_serializer.py")
EXTRACTION_AUGMENTER = Path(
    "src/standards_atlas/application/formal_semantics/extraction_projector.py"
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_projector_remains_independent_of_rdf_and_graph_providers() -> None:
    imports = _imports(PROJECTOR)
    assert not any(name.startswith(("rdflib", "neo4j", "graphrag")) for name in imports)


def test_rdf_representation_is_kept_in_adapter_layer() -> None:
    assert RDF_ADAPTER.is_file()
    assert "adapters/rdf" not in PROJECTOR.as_posix()


def test_proposal_extraction_has_no_direct_abox_augmentation_path() -> None:
    assert not EXTRACTION_AUGMENTER.exists()
    imports = _imports(PROJECTOR)
    assert "standards_atlas.domain.model.semantic_extraction" not in imports
    assert "standards_atlas.application.knowledge_proposal_extraction" not in imports
